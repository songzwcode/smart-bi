"""SQL Agent (Query Mode main loop).

Plan → for each step: nl2sql → execute (with self-correction) → render.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.agent.intent import classify_intent, classify_intent_stream, IntentResult
from backend.agent.prompts import load as load_prompt
from backend.agent.planner import Plan, PlanStep, make_plan, make_plan_stream
from backend.agent.self_correct import _strip_sql, correct_sql
from backend.config import get_settings
from backend.data.cache import get_cache
from backend.data.connector import Database, get_database
from backend.data.introspect import SchemaInfo, introspect_schema
from backend.data.safety import check_sql_safety
from backend.data.schema_rag import get_schema_rag
from backend.llm.base import LLMClient, Message
from backend.utils import AgentError, DBError, SQLError, get_logger

log = get_logger(__name__)


@dataclass
class StepResult:
    description: str
    sql: str
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    error: str = ""
    thinking: str = ""  # reasoning-model thinking captured during this step


@dataclass
class QueryResult:
    question: str
    intent: IntentResult
    plan: Plan
    steps: list[StepResult] = field(default_factory=list)
    final_sql: str = ""
    final_columns: list[str] = field(default_factory=list)
    final_rows: list[list] = field(default_factory=list)
    chart: Optional[dict] = None
    chart_type: Optional[str] = None  # resolved (explicit OR intent-derived)
    chart_auto: bool = False           # True if chart came from intent, not manual selector
    elapsed_ms: int = 0
    llm_model: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "intent": {
                "intent": self.intent.intent,
                "confidence": self.intent.confidence,
                "params": self.intent.params,
                "reasoning": self.intent.reasoning,
                "thinking": self.intent.thinking,
            },
            "plan": self.plan.to_dict(),
            "steps": [s.__dict__ for s in self.steps],
            "final_sql": self.final_sql,
            "final_columns": self.final_columns,
            "final_rows": self.final_rows,
            "chart": self.chart,
            "chart_type": self.chart_type,
            "chart_auto": self.chart_auto,
            "elapsed_ms": self.elapsed_ms,
            "llm_model": self.llm_model,
        }


def _build_few_shot_block() -> str:
    s = get_settings()
    if not s.agent.enable_few_shot:
        return ""
    p = Path(__file__).parent / "prompts" / "few_shots.json"
    if not p.exists():
        return ""
    try:
        samples = json.loads(p.read_text(encoding="utf-8"))[: s.agent.few_shot_count]
    except Exception:
        return ""
    lines = ["# Few-shot examples"]
    for i, ex in enumerate(samples, 1):
        lines.append(f"\n## Example {i}\nQ: {ex['question']}\nA: ```sql\n{ex['sql']}\n```")
    return "\n".join(lines)


# Map a chart-related keyword found in the question to a specific chart type.
# Order matters: more specific patterns first.
_CHART_TYPE_PATTERNS: list[tuple[str, str]] = [
    # pie
    (r"饼图|pie", "pie"),
    # line / trend over time
    (r"折线|趋势|line|trend", "line"),
    # scatter
    (r"散点|scatter", "scatter"),
    # area
    (r"面积|area", "area"),
    # bar (柱状/柱形/条形/条形图/对比/排行/排名/分布)
    (r"柱状|柱形|条形|对比|排行|排名|分布|bar", "bar"),
    # generic
    (r"画|图表|可视化|chart|graph|plot|可视化", "bar"),
]

_CHART_HINT_RE = re.compile(
    r"(画|图表|可视化|柱状|柱形|条形|饼图|折线|散点|面积|对比|排行|排名|分布|chart|graph|plot|bar chart|line chart|pie chart)",
    re.IGNORECASE,
)


def _resolve_chart_type(
    intent: "IntentResult",
    question: str,
    explicit: Optional[str] = None,
) -> Optional[str]:
    """Decide the effective chart type, in priority order:
    1) Explicit `chart_type` arg from the caller (manual UI selector wins).
    2) Intent classifier chose `generate_chart` and provided chart_type.
    3) Question text contains a chart keyword → derive a specific type.
    Returns None if no chart should be rendered.
    """
    if explicit:
        return explicit
    params = intent.params or {}
    # Intent gave us a chart_type directly (works for both query_data and
    # generate_chart intents — e.g. "按品类统计销售额并画饼图" still ends up
    # here as query_data with chart_type=pie).
    ct = params.get("chart_type")
    if isinstance(ct, str) and ct.strip():
        return ct.strip().lower()
    # Intent is generate_chart but no chart_type — try the text heuristic
    # so "画饼图" still produces a pie chart even if intent params dropped it.
    if intent.intent == "generate_chart" and _CHART_HINT_RE.search(question):
        return _chart_type_from_text(question)
    if intent.intent == "generate_chart":
        return "bar"
    # Last-resort text heuristic for query_data with chart-y phrasing
    if _CHART_HINT_RE.search(question):
        return _chart_type_from_text(question)
    return None


def _chart_type_from_text(question: str) -> str:
    for pattern, ct in _CHART_TYPE_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return ct
    return "bar"


def _intent_hint(intent: "IntentResult") -> str:
    """Format intent params as a structured hint appended to the sub-question,
    so the SQL generator knows which metric/dimension/aggregation to use
    (especially important when the intent classifier already figured them
    out and the LLM would otherwise re-derive them from scratch)."""
    params = intent.params or {}
    keep = {
        k: v
        for k, v in params.items()
        if k in ("metric", "dimension", "aggregation", "time_range", "group_by", "chart_type")
        and v
    }
    if not keep:
        return ""
    lines = ["\n# 已识别参数（请在 SQL 中体现）"]
    for k, v in keep.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _generate_sql(
    llm: LLMClient,
    question: str,
    schema_text: str,
    rag_context: str,
    few_shot_block: str,
) -> str:
    s = get_settings()
    system_prompt = load_prompt("nl2sql").format(
        dialect=s.output.sql_dialect_default,
        schema_text=schema_text,
        rag_context=rag_context,
        few_shot_block=few_shot_block,
        question=question,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=question),
    ]
    resp = llm.chat(messages, temperature=0.1)
    return _strip_sql(resp.content), resp.thinking or ""


def _generate_sql_stream(llm, sub_question, schema_text, rag_context, few_shot_block):
    """Streaming variant of _generate_sql. Yields (event_dict, None) for
    each LLM chunk, then (None, (sql, thinking))."""
    s = get_settings()
    system_prompt = load_prompt("nl2sql").format(
        dialect=s.output.sql_dialect_default,
        schema_text=schema_text,
        rag_context=rag_context,
        few_shot_block=few_shot_block,
        question=sub_question,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=sub_question),
    ]
    full_content: list[str] = []
    full_thinking: list[str] = []
    try:
        for ev in llm.chat_stream(messages, temperature=0.1):
            t = ev.get("type")
            if t == "think":
                full_thinking.append(ev.get("text", ""))
                yield ev, None
            elif t == "content":
                full_content.append(ev.get("text", ""))
                yield ev, None
            elif t == "done":
                if not ev.get("content") and not full_content:
                    # Streaming produced nothing — fall back to non-streaming
                    resp = llm.chat(messages, temperature=0.1)
                    full_content.append(resp.content)
                    full_thinking.append(resp.thinking or "")
    except Exception as e:
        log.warning(f"Streaming SQL gen failed, falling back to non-stream: {e}")
        resp = llm.chat(messages, temperature=0.1)
        full_content.append(resp.content)
        full_thinking.append(resp.thinking or "")

    sql = _strip_sql("".join(full_content))
    thinking = "".join(full_thinking)
    yield None, (sql, thinking)


def _run_step(
    llm: LLMClient,
    db: Database,
    step: PlanStep,
    question: str,
    schema_text: str,
    schema_info: SchemaInfo,
    rag_context: str,
    few_shot_block: str,
    max_rounds: int,
    intent_hint: str = "",
) -> StepResult:
    """Run a single planner step: generate SQL → execute → self-correct if needed."""
    sub_question = step.description or question
    if intent_hint:
        sub_question = f"{sub_question}\n{intent_hint}"
    sql, thinking = _generate_sql(llm, sub_question, schema_text, rag_context, few_shot_block)

    # safety
    safety = check_sql_safety(sql)
    if not safety.ok:
        return StepResult(
            description=step.description, sql=sql,
            error=f"SQL rejected by safety: {safety.reason}",
            thinking=thinking,
        )

    last_err: Optional[str] = None
    for round_idx in range(max_rounds + 1):
        try:
            cols, rows = db.fetch_rows(sql, max_rows=get_settings().database.max_rows)
            return StepResult(
                description=step.description, sql=sql, columns=cols, rows=rows,
                thinking=thinking,
            )
        except Exception as e:
            last_err = str(e)
            log.warning(f"SQL execution failed (round {round_idx}): {e}")
            if round_idx >= max_rounds:
                break
            try:
                sql = correct_sql(
                    llm,
                    original_sql=sql,
                    error_message=last_err,
                    schema_text=schema_text,
                    system_prompt=load_prompt("nl2sql").format(
                        dialect=get_settings().output.sql_dialect_default,
                        schema_text=schema_text,
                        rag_context="",
                        few_shot_block="",
                        question=sub_question,
                    ),
                )
                # capture thinking from correction round too
                # correct_sql returns the SQL string only; we don't have
                # the LLMResponse here. Acceptable trade-off — the user's
                # main ask is to surface the planning-time reasoning.
                safety = check_sql_safety(sql)
                if not safety.ok:
                    return StepResult(
                        description=step.description, sql=sql,
                        error=f"Corrected SQL rejected: {safety.reason}",
                        thinking=thinking,
                    )
            except Exception as e2:
                last_err = f"{last_err} | correction failed: {e2}"
                break

    return StepResult(
        description=step.description, sql=sql,
        error=last_err or "Unknown error", thinking=thinking,
    )


def _make_chart_from_result(
    result: StepResult,
    chart_type: str,
) -> Optional[dict]:
    """Build a Plotly chart JSON from the result rows."""
    if not result.rows or not result.columns:
        return None
    try:
        df = pd.DataFrame(result.rows, columns=result.columns)
    except Exception:
        return None
    if df.empty or len(df.columns) < 2:
        return None
    # Heuristic: first non-numeric col is x; first numeric col is y.
    # On pandas 2.x+ string columns can have `object` OR the new `str`
    # extension dtype, so accept both.
    def _is_categorical(s: pd.Series) -> bool:
        return s.dtype == object or pd.api.types.is_string_dtype(s)

    x_col = None
    y_col = None
    for c in df.columns:
        if x_col is None and _is_categorical(df[c]):
            x_col = c
        elif y_col is None and pd.api.types.is_numeric_dtype(df[c]):
            y_col = c
    if not x_col or not y_col:
        return None

    from backend.output.chart import make_chart

    return make_chart(df, chart_type=chart_type, x=x_col, y=y_col)


def run_query(
    question: str,
    llm: LLMClient,
    *,
    db: Optional[Database] = None,
    chart_type: Optional[str] = None,
) -> QueryResult:
    """Run a full Query Mode cycle."""
    import time

    t0 = time.time()
    s = get_settings()
    db = db or get_database()

    # 1. Introspect + RAG
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()
    rag_context = ""
    if s.agent.enable_schema_rag:
        try:
            rag = get_schema_rag()
            if rag.version == 0:
                rag.reindex(schema_info)
            rag_context = rag.context_for(question, top_k=s.agent.schema_rag_top_k)
        except Exception as e:
            log.warning(f"SchemaRAG failed: {e}")

    few_shot_block = _build_few_shot_block()

    # 2. Intent classification
    intent = classify_intent(llm, question, system_prompt=load_prompt("intent"))

    # 2a. Resolve effective chart type. If the LLM picked up "画饼图" in the
    # question (or the caller passed one explicitly), we render a chart even
    # though the user didn't click the manual chart-type dropdown.
    effective_chart_type = _resolve_chart_type(intent, question, chart_type)
    intent_hint = _intent_hint(intent)

    # 3. Plan
    plan = Plan(is_multi_step=False, steps=[])
    if s.agent.enable_planner:
        plan = make_plan(
            llm,
            question,
            system_prompt=load_prompt("planner"),
            max_steps=s.agent.max_plan_steps,
        )

    if not plan.steps:
        plan = Plan(
            is_multi_step=False,
            steps=[PlanStep(id=1, description=question, action="nl2sql")],
        )

    # 4. Execute steps
    results: list[StepResult] = []
    for step in plan.steps:
        r = _run_step(
            llm, db, step, question, schema_text, schema_info, rag_context, few_shot_block,
            max_rounds=s.agent.max_self_correct_rounds,
            intent_hint=intent_hint,
        )
        results.append(r)
        if r.error:
            log.warning(f"Step {step.id} failed: {r.error}")

    # 5. Final result = last successful step
    final: Optional[StepResult] = next((r for r in reversed(results) if not r.error), None)
    chart = None
    if final and effective_chart_type:
        chart = _make_chart_from_result(final, effective_chart_type)

    elapsed_ms = int((time.time() - t0) * 1000)
    return QueryResult(
        question=question,
        intent=intent,
        plan=plan,
        steps=results,
        final_sql=final.sql if final else "",
        final_columns=final.columns if final else [],
        final_rows=final.rows if final else [],
        chart=chart,
        chart_type=effective_chart_type,
        chart_auto=(not chart_type) and bool(effective_chart_type),
        elapsed_ms=elapsed_ms,
        llm_model=llm.model,
    )


def run_query_stream(
    question: str,
    llm: LLMClient,
    *,
    db: Optional[Database] = None,
    chart_type: Optional[str] = None,
):
    """Streaming variant. Yields (event_dict, None) for each chunk,
    then finally yields (None, QueryResult)."""
    import time

    t0 = time.time()
    s = get_settings()
    db = db or get_database()

    # 1. Introspect + RAG (no LLM)
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()
    rag_context = ""
    if s.agent.enable_schema_rag:
        try:
            rag = get_schema_rag()
            if rag.version == 0:
                rag.reindex(schema_info)
            rag_context = rag.context_for(question, top_k=s.agent.schema_rag_top_k)
        except Exception as e:
            log.warning(f"SchemaRAG failed: {e}")

    few_shot_block = _build_few_shot_block()

    # 2. Intent (streamed)
    yield {"type": "phase", "phase": "intent"}, None
    intent: Optional[IntentResult] = None
    for ev, result in classify_intent_stream(llm, question, system_prompt=load_prompt("intent")):
        if ev is not None:
            yield ev, None
        if result is not None:
            intent = result
    if intent is None:
        intent = IntentResult(intent="query_data", confidence=0.5, params={})

    # 2a. Resolve effective chart type from intent + question text.
    effective_chart_type = _resolve_chart_type(intent, question, chart_type)
    intent_hint = _intent_hint(intent)

    # 3. Plan (streamed)
    yield {"type": "phase", "phase": "plan"}, None
    plan: Plan = Plan(is_multi_step=False, steps=[])
    if s.agent.enable_planner:
        for ev, result in make_plan_stream(llm, question, system_prompt=load_prompt("planner"), max_steps=s.agent.max_plan_steps):
            if ev is not None:
                yield ev, None
            if result is not None:
                plan = result

    if not plan.steps:
        plan = Plan(
            is_multi_step=False,
            steps=[PlanStep(id=1, description=question, action="nl2sql")],
        )

    yield {"type": "plan_ready", "plan": plan.to_dict()}, None

    # 4. Execute steps (with streamed SQL gen)
    results: list[StepResult] = []
    for step in plan.steps:
        yield {"type": "phase", "phase": "step", "step_id": step.id, "description": step.description}, None

        # Sub-question may be augmented with structured intent params so the
        # LLM doesn't have to re-derive metric/dimension/aggregation.
        sub_q = step.description or question
        if intent_hint:
            sub_q = f"{sub_q}\n{intent_hint}"

        # Stream SQL generation
        sql = ""
        thinking = ""
        for ev, payload in _generate_sql_stream(llm, sub_q, schema_text, rag_context, few_shot_block):
            if ev is not None:
                yield ev, None
            if payload is not None:
                sql, thinking = payload

        # Safety + execute
        safety = check_sql_safety(sql)
        if not safety.ok:
            results.append(StepResult(description=step.description, sql=sql,
                                       error=f"SQL rejected by safety: {safety.reason}", thinking=thinking))
            yield {"type": "step_done", "step": results[-1].__dict__}, None
            continue

        # Try execute + self-correct
        last_err: Optional[str] = None
        for round_idx in range(s.agent.max_self_correct_rounds + 1):
            try:
                cols, rows = db.fetch_rows(sql, max_rows=s.database.max_rows)
                results.append(StepResult(description=step.description, sql=sql, columns=cols, rows=rows, thinking=thinking))
                last_err = None
                break
            except Exception as e:
                last_err = str(e)
                log.warning(f"SQL execution failed (round {round_idx}): {e}")
                if round_idx >= s.agent.max_self_correct_rounds:
                    break
                try:
                    sql = correct_sql(
                        llm,
                        original_sql=sql,
                        error_message=last_err,
                        schema_text=schema_text,
                        system_prompt=load_prompt("nl2sql").format(
                            dialect=s.output.sql_dialect_default,
                            schema_text=schema_text,
                            rag_context="",
                            few_shot_block="",
                            question=step.description or question,
                        ),
                    )
                    safety = check_sql_safety(sql)
                    if not safety.ok:
                        results.append(StepResult(description=step.description, sql=sql,
                                                   error=f"Corrected SQL rejected: {safety.reason}", thinking=thinking))
                        last_err = None
                        break
                except Exception as e2:
                    last_err = f"{last_err} | correction failed: {e2}"
                    break
        else:
            pass

        if last_err is not None and (not results or results[-1].sql != sql):
            results.append(StepResult(description=step.description, sql=sql, error=last_err, thinking=thinking))

        if results and results[-1].sql == sql:
            yield {"type": "step_done", "step": results[-1].__dict__}, None

    # 5. Final
    final: Optional[StepResult] = next((r for r in reversed(results) if not r.error), None)
    chart = None
    if final and effective_chart_type:
        chart = _make_chart_from_result(final, effective_chart_type)

    elapsed_ms = int((time.time() - t0) * 1000)
    qr = QueryResult(
        question=question,
        intent=intent,
        plan=plan,
        steps=results,
        final_sql=final.sql if final else "",
        final_columns=final.columns if final else [],
        final_rows=final.rows if final else [],
        chart=chart,
        chart_type=effective_chart_type,
        chart_auto=(not chart_type) and bool(effective_chart_type),
        elapsed_ms=elapsed_ms,
        llm_model=llm.model,
    )
    yield {"type": "final", "result": qr.to_dict()}, qr
