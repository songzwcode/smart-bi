"""Script Agent (Script Mode main loop).

Generates SQL or stored procedure code from natural language, with optional
refinement based on user feedback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from backend.agent.intent import classify_intent, IntentResult
from backend.agent.prompts import load as load_prompt
from backend.agent.self_correct import _strip_sql
from backend.config import get_settings
from backend.data.connector import get_database
from backend.data.introspect import introspect_schema
from backend.llm.base import LLMClient, Message
from backend.utils import AgentError, get_logger

log = get_logger(__name__)


@dataclass
class ScriptResult:
    requirement: str
    code: str
    language: str = "sql"        # sql | mysql | postgres
    script_subtype: str = "query"  # query | dml | procedure
    intent: Optional[IntentResult] = None
    elapsed_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "code": self.code,
            "language": self.language,
            "script_subtype": self.script_subtype,
            "intent": self.intent.__dict__ if self.intent else None,
            "elapsed_ms": self.elapsed_ms,
        }


def _detect_dialect() -> str:
    s = get_settings()
    db = get_database()
    return db.dialect   # sqlite | mysql | postgres | other


def _pick_prompt_template(script_subtype: str, dialect: str) -> str:
    if script_subtype == "procedure":
        if dialect == "mysql":
            return load_prompt("sp_mysql")
        if dialect in ("postgres", "postgresql"):
            return load_prompt("sp_postgres")
        # fall back to mysql template (close enough for unknown dialects)
        return load_prompt("sp_mysql")
    return load_prompt("nl2sql")


def generate_script(
    requirement: str,
    llm: LLMClient,
    *,
    script_subtype: Optional[str] = None,
    chart_type: Optional[str] = None,   # ignored for scripts
) -> ScriptResult:
    """Generate a SQL/SP from a natural-language requirement."""
    import time

    t0 = time.time()
    s = get_settings()
    db = get_database()
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()
    dialect = _detect_dialect()

    # Classify intent to pick the right template
    intent = classify_intent(llm, requirement, system_prompt=load_prompt("intent"))
    sub = script_subtype or intent.params.get("script_subtype") or "query"
    if sub not in ("query", "dml", "procedure"):
        sub = "query"

    template = _pick_prompt_template(sub, dialect)
    system_prompt = template.format(
        dialect=dialect,
        schema_text=schema_text,
        rag_context="",
        few_shot_block="",
        question=requirement,
        requirement=requirement,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=requirement),
    ]
    resp = llm.chat(messages, temperature=0.2)
    code = _strip_sql(resp.content) if sub != "procedure" else _strip_code_block(resp.content)

    elapsed_ms = int((time.time() - t0) * 1000)
    return ScriptResult(
        requirement=requirement,
        code=code,
        language="mysql" if dialect == "mysql" else "postgres" if dialect in ("postgres", "postgresql") else "sql",
        script_subtype=sub,
        intent=intent,
        elapsed_ms=elapsed_ms,
    )


def refine_script(
    original_sql: str,
    feedback: str,
    llm: LLMClient,
) -> ScriptResult:
    """Iteratively modify a script based on user feedback."""
    import time

    t0 = time.time()
    db = get_database()
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()

    system_prompt = load_prompt("script_refine").format(
        original_sql=original_sql,
        schema_text=schema_text,
        feedback=feedback,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=feedback),
    ]
    resp = llm.chat(messages, temperature=0.2)
    code = _strip_code_block(resp.content)

    elapsed_ms = int((time.time() - t0) * 1000)
    return ScriptResult(
        requirement=feedback,
        code=code,
        language="sql",
        script_subtype="query",
        elapsed_ms=elapsed_ms,
    )


# ---- streaming variants ------------------------------------------------------


def _stream_llm_code(llm, messages):
    """Stream the LLM and yield (event, payload) tuples. `event` is the
    chunk dict for the SSE consumer; `payload` is the final stripped code
    string (or None mid-stream)."""
    full_content: list[str] = []
    full_thinking: list[str] = []
    produced_anything = False
    try:
        for ev in llm.chat_stream(messages, temperature=0.2):
            t = ev.get("type")
            if t == "think":
                full_thinking.append(ev.get("text", ""))
                yield ev, None
            elif t == "content":
                full_content.append(ev.get("text", ""))
                produced_anything = True
                yield ev, None
            elif t == "done":
                # If the stream produced nothing, fall back to non-streaming
                if not produced_anything and not full_content:
                    resp = llm.chat(messages, temperature=0.2)
                    full_content.append(resp.content)
                    full_thinking.append(resp.thinking or "")
    except Exception as e:
        log.warning(f"Streaming LLM code failed, falling back to non-stream: {e}")
        if not full_content:
            resp = llm.chat(messages, temperature=0.2)
            full_content.append(resp.content)
            full_thinking.append(resp.thinking or "")

    raw = "".join(full_content)
    yield None, (raw, "".join(full_thinking))


def generate_script_stream(
    requirement: str,
    llm: LLMClient,
    *,
    script_subtype: Optional[str] = None,
):
    """Streaming variant of generate_script. Yields (event_dict, None) for
    each chunk, then (None, ScriptResult) at the end.

    Events:
      - {type: "phase", phase: "intent" | "code"}
      - {type: "think", text: "..."}
      - {type: "content", text: "..."}    (raw, un-stripped code text)
      - {type: "final", result: {...}}
      - {type: "error", error: "..."}
    """
    import time

    t0 = time.time()
    s = get_settings()
    db = get_database()
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()
    dialect = _detect_dialect()

    # Intent classification (non-streaming for now — it's fast)
    yield {"type": "phase", "phase": "intent"}, None
    intent = classify_intent(llm, requirement, system_prompt=load_prompt("intent"))
    sub = script_subtype or intent.params.get("script_subtype") or "query"
    if sub not in ("query", "dml", "procedure"):
        sub = "query"

    template = _pick_prompt_template(sub, dialect)
    system_prompt = template.format(
        dialect=dialect,
        schema_text=schema_text,
        rag_context="",
        few_shot_block="",
        question=requirement,
        requirement=requirement,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=requirement),
    ]

    # Code generation (streamed)
    yield {"type": "phase", "phase": "code"}, None
    raw_text = ""
    thinking = ""
    for ev, payload in _stream_llm_code(llm, messages):
        if ev is not None:
            yield ev, None
        if payload is not None:
            raw_text, thinking = payload

    # Strip code fences / SQL markdown at the end
    code = _strip_sql(raw_text) if sub != "procedure" else _strip_code_block(raw_text)

    elapsed_ms = int((time.time() - t0) * 1000)
    result = ScriptResult(
        requirement=requirement,
        code=code,
        language="mysql" if dialect == "mysql" else "postgres" if dialect in ("postgres", "postgresql") else "sql",
        script_subtype=sub,
        intent=intent,
        elapsed_ms=elapsed_ms,
    )
    yield {"type": "final", "result": result.to_dict()}, result


def refine_script_stream(
    original_sql: str,
    feedback: str,
    llm: LLMClient,
):
    """Streaming variant of refine_script. Same event contract as
    generate_script_stream (without the intent phase)."""
    import time

    t0 = time.time()
    db = get_database()
    schema_info = introspect_schema(db)
    schema_text = schema_info.schema_text()

    system_prompt = load_prompt("script_refine").format(
        original_sql=original_sql,
        schema_text=schema_text,
        feedback=feedback,
    )
    messages = [
        Message(role="system", content=system_prompt),
        Message(role="user", content=feedback),
    ]

    yield {"type": "phase", "phase": "code"}, None
    raw_text = ""
    thinking = ""
    for ev, payload in _stream_llm_code(llm, messages):
        if ev is not None:
            yield ev, None
        if payload is not None:
            raw_text, thinking = payload

    code = _strip_code_block(raw_text)

    elapsed_ms = int((time.time() - t0) * 1000)
    result = ScriptResult(
        requirement=feedback,
        code=code,
        language="sql",
        script_subtype="query",
        elapsed_ms=elapsed_ms,
    )
    yield {"type": "final", "result": result.to_dict()}, result


def _strip_code_block(text: str) -> str:
    """Strip ```sql / ```mysql fences. Preserves internal content as-is."""
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
