"""REST API routes."""
from __future__ import annotations

import os
import threading
from typing import Optional

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from backend.agent.script_agent import generate_script, generate_script_stream, refine_script, refine_script_stream
from backend.agent.sql_agent import run_query
from backend.api.schemas import (
    ConnectionConfig,
    ConnectionTestRequest,
    ExecuteSQLRequest,
    FormatSQLRequest,
    HealthResponse,
    LLMInfo,
    LLMSwitchRequest,
    QueryRequest,
    QueryResponse,
    SchemaResponse,
    ScriptRefineRequest,
    ScriptRequest,
    ScriptResponse,
)
from backend.config import get_settings, reload_settings
from backend.data.connector import get_database, switch_database
from backend.data.introspect import introspect_schema
from backend.data.safety import check_sql_safety
from backend.data.schema_rag import get_schema_rag
from backend.llm.factory import create_llm, list_available_llms
from backend.output.formatter import format_sql, lint_sql
from backend.utils import DBError, LLMError, SQLError, get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/api")


# ---- LLM singleton state ----------------------------------------------------


class LLMState:
    """Thread-safe holder for the currently-active LLM client."""

    def __init__(self):
        self._lock = threading.RLock()
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self._client = None
        # try to auto-detect
        self._auto_init()

    def _auto_init(self):
        from backend.data.user_settings import get_llm
        from backend.llm_detect import detect_default_llm

        # 1) Persisted user choice wins
        saved = get_llm()
        if saved and saved.get("provider"):
            try:
                kwargs = {}
                if saved.get("ollama_url"):
                    kwargs["ollama_url"] = saved["ollama_url"]
                if saved.get("custom_url"):
                    kwargs["custom_url"] = saved["custom_url"]
                if saved.get("custom_api_key"):
                    kwargs["custom_api_key"] = saved["custom_api_key"]
                self._set(saved["provider"], saved.get("model"), **kwargs)
                log.info(
                    f"Restored LLM from user settings: {saved['provider']}"
                    f"{' · ' + saved['model'] if saved.get('model') else ''}"
                )
                return
            except Exception as e:
                log.warning(f"Failed to restore saved LLM, falling back to detect: {e}")

        # 2) Auto-detect
        provider, model = detect_default_llm()
        if provider and model:
            try:
                self._set(provider, model)
            except Exception as e:
                log.warning(f"Auto-init LLM failed: {e}")

    def _set(self, provider: str, model: Optional[str] = None, **kwargs):
        from backend.llm.factory import create_llm

        client = create_llm(provider=provider, model=model, **kwargs)
        with self._lock:
            self._client = client
            self.provider = provider
            self.model = client.model

    def get(self):
        with self._lock:
            if self._client is None:
                raise LLMError(
                    "No LLM is configured",
                    hint="Set OPENAI_API_KEY / ANTHROPIC_API_KEY or install Ollama, "
                    "or switch to a Custom / OpenAI-compatible endpoint in Settings.",
                )
            return self._client

    def switch(self, provider: str, model: Optional[str] = None, **kwargs):
        self._set(provider, model, **kwargs)


_state = LLMState()


# ---- routes -----------------------------------------------------------------


@router.get("/health", response_model=HealthResponse)
def health():
    db = get_database()
    return HealthResponse(
        ok=True,
        app=get_settings().app.name,
        version=get_settings().app.version,
        llm_provider=_state.provider,
        llm_model=_state.model or "",
        db_url=db.url,
        db_dialect=db.dialect,
    )


@router.get("/schema", response_model=SchemaResponse)
def get_schema(reindex: bool = False):
    db = get_database()
    info = introspect_schema(db)
    reindexed = False
    if reindex:
        try:
            get_schema_rag().reindex(info)
            reindexed = True
        except Exception as e:
            log.warning(f"Reindex failed: {e}")
    return SchemaResponse(
        database=info.database,
        dialect=info.dialect,
        tables=[t.to_dict() for t in info.tables],
        schema_text=info.schema_text(),
        reindexed=reindexed,
    )


@router.post("/connection/test")
def test_connection(req: ConnectionTestRequest):
    try:
        from backend.data.connector import Database

        url = req.config.to_url()
        db = Database(url, readonly=req.readonly)
        result = db.test_connection()
        try:
            db.dispose()
        except Exception:
            pass
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/connection/connect")
def connect(req: ConnectionConfig, readonly: bool = True):
    try:
        url = req.to_url()
        db = switch_database(url, readonly=readonly)
        # reindex schema RAG in background
        try:
            get_schema_rag().reindex(introspect_schema(db))
        except Exception as e:
            log.warning(f"Reindex on connect failed: {e}")
        # Persist so the same DB comes back on restart.
        from backend.data.user_settings import set_db
        set_db(req.model_dump())
        return {"ok": True, "url": db.url, "dialect": db.dialect}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/llm/list", response_model=LLMInfo)
def list_llms():
    return LLMInfo(
        current_provider=_state.provider or "",
        current_model=_state.model or "",
        available=list_available_llms(),
    )


@router.post("/llm/switch", response_model=LLMInfo)
def switch_llm(req: LLMSwitchRequest):
    try:
        # Apply api_key into env if provided
        if req.api_key:
            if req.provider == "openai":
                os.environ["OPENAI_API_KEY"] = req.api_key
            elif req.provider in ("anthropic", "claude"):
                os.environ["ANTHROPIC_API_KEY"] = req.api_key
            elif req.provider == "custom":
                os.environ["CUSTOM_LLM_API_KEY"] = req.api_key
        kwargs = {}
        if req.ollama_url:
            kwargs["ollama_url"] = req.ollama_url
        if req.custom_url:
            kwargs["custom_url"] = req.custom_url
        if req.provider == "custom" and req.api_key:
            kwargs["custom_api_key"] = req.api_key
        _state.switch(req.provider, req.model, **kwargs)
        # Persist so the same LLM comes back on restart.
        from backend.data.user_settings import set_llm
        set_llm(
            provider=req.provider,
            model=req.model,
            ollama_url=req.ollama_url,
            custom_url=req.custom_url,
            custom_api_key=kwargs.get("custom_api_key"),
        )
        return LLMInfo(
            current_provider=_state.provider or "",
            current_model=_state.model or "",
            available=list_available_llms(),
        )
    except LLMError as e:
        raise HTTPException(status_code=400, detail=e.to_dict())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/llm/test")
def test_llm(provider: str, model: Optional[str] = None, custom_url: Optional[str] = None,
             api_key: Optional[str] = None, ollama_url: Optional[str] = None):
    """Probe a provider endpoint without committing to a switch."""
    try:
        from backend.llm.factory import create_llm

        kwargs: dict = {}
        if ollama_url:
            kwargs["ollama_url"] = ollama_url
        if custom_url:
            kwargs["custom_url"] = custom_url
        if api_key:
            kwargs["custom_api_key"] = api_key
        client = create_llm(provider=provider, model=model, **kwargs)
        if hasattr(client, "test_connectivity"):
            return client.test_connectivity()
        # Fallback: just instantiate — assume OK
        return {"ok": True, "provider": provider, "model": client.model}
    except LLMError as e:
        return {"ok": False, "error": e.message, "hint": e.hint}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    try:
        llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()
        result = run_query(
            req.question,
            llm,
            chart_type=req.chart_type,
        )
        return QueryResponse(
            success=True,
            question=result.question,
            intent=result.intent.__dict__,
            plan=result.plan.to_dict(),
            steps=[s.__dict__ for s in result.steps],
            final_sql=result.final_sql,
            columns=result.final_columns,
            rows=result.final_rows,
            chart=result.chart,
            chart_type=result.chart_type,
            chart_auto=result.chart_auto,
            elapsed_ms=result.elapsed_ms,
            llm_model=result.llm_model,
        )
    except LLMError as e:
        return QueryResponse(success=False, question=req.question, error=str(e), intent={}, plan={}, steps=[], final_sql="")
    except DBError as e:
        return QueryResponse(success=False, question=req.question, error=str(e), intent={}, plan={}, steps=[], final_sql="")
    except Exception as e:
        log.exception("Query failed")
        return QueryResponse(success=False, question=req.question, error=str(e), intent={}, plan={}, steps=[], final_sql="")


@router.post("/query/stream")
async def query_stream(req: QueryRequest):
    """SSE streaming variant. Emits:
      - phase: { phase: "intent"|"plan"|"step", ... }
      - think: { text: "..." }      (reasoning chunk from LLM)
      - content: { text: "..." }   (visible answer chunk)
      - plan_ready: { plan: {...} }
      - step_done: { step: {...} }
      - final: { result: {...} }
      - error: { error: "..." }
    """
    import asyncio
    import json

    async def event_gen():
        try:
            llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()

            # Run the streaming agent in a thread so we can yield to the
            # event loop. The agent yields (event, result) tuples.
            from backend.agent.sql_agent import run_query_stream

            queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _run():
                try:
                    for ev, _result in run_query_stream(
                        req.question, llm, chart_type=req.chart_type
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, ev)
                except Exception as e:
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        {"type": "error", "error": str(e)},
                    )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()

            while True:
                ev = await queue.get()
                if ev is None:
                    break
                t = ev.get("type")
                if t == "phase":
                    yield {"event": "phase", "data": json.dumps(ev, ensure_ascii=False)}
                elif t == "think":
                    yield {"event": "think", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "content":
                    yield {"event": "content", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "plan_ready":
                    yield {"event": "plan", "data": json.dumps(ev.get("plan", {}), ensure_ascii=False, default=str)}
                elif t == "step_done":
                    yield {"event": "step", "data": json.dumps(ev.get("step", {}), ensure_ascii=False, default=str)}
                elif t == "final":
                    yield {"event": "final", "data": json.dumps(ev.get("result", {}), ensure_ascii=False, default=str)}
                elif t == "error":
                    yield {"event": "error", "data": json.dumps({"error": ev.get("error", "")}, ensure_ascii=False)}
        except Exception as e:
            log.exception("Stream failed")
            yield {"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_gen())


@router.post("/script", response_model=ScriptResponse)
def script(req: ScriptRequest):
    try:
        llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()
        result = generate_script(req.requirement, llm, script_subtype=req.script_subtype)
        return ScriptResponse(
            success=True,
            requirement=result.requirement,
            code=result.code,
            language=result.language,
            script_subtype=result.script_subtype,
            intent=result.intent.__dict__ if result.intent else None,
            elapsed_ms=result.elapsed_ms,
        )
    except LLMError as e:
        return ScriptResponse(success=False, requirement=req.requirement, code="", language="sql", script_subtype="query", error=str(e))
    except Exception as e:
        log.exception("Script failed")
        return ScriptResponse(success=False, requirement=req.requirement, code="", language="sql", script_subtype="query", error=str(e))


@router.post("/script/refine", response_model=ScriptResponse)
def script_refine(req: ScriptRefineRequest):
    try:
        llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()
        result = refine_script(req.original_sql, req.feedback, llm)
        return ScriptResponse(
            success=True,
            requirement=result.requirement,
            code=result.code,
            language=result.language,
            script_subtype=result.script_subtype,
            elapsed_ms=result.elapsed_ms,
        )
    except Exception as e:
        log.exception("Script refine failed")
        return ScriptResponse(success=False, requirement=req.feedback, code=req.original_sql, language="sql", script_subtype="query", error=str(e))


@router.post("/script/stream")
async def script_stream(req: ScriptRequest):
    """SSE streaming variant of /api/script. Emits:
      - phase: { phase: "intent" | "code" }
      - think: { text: "..." }
      - content: { text: "..." }   (raw code chunk)
      - final: { result: {...} }
      - error: { error: "..." }
    """
    import asyncio
    import json

    async def event_gen():
        try:
            llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()
            queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _run():
                try:
                    for ev, _result in generate_script_stream(
                        req.requirement, llm, script_subtype=req.script_subtype
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, ev)
                except Exception as e:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "error": str(e)}
                    )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=_run, daemon=True).start()

            while True:
                ev = await queue.get()
                if ev is None:
                    break
                t = ev.get("type")
                if t == "phase":
                    yield {"event": "phase", "data": json.dumps(ev, ensure_ascii=False)}
                elif t == "think":
                    yield {"event": "think", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "content":
                    yield {"event": "content", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "final":
                    yield {"event": "final", "data": json.dumps(ev.get("result", {}), ensure_ascii=False, default=str)}
                elif t == "error":
                    yield {"event": "error", "data": json.dumps({"error": ev.get("error", "")}, ensure_ascii=False)}
        except Exception as e:
            log.exception("Script stream failed")
            yield {"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_gen())


@router.post("/script/refine/stream")
async def script_refine_stream(req: ScriptRefineRequest):
    """SSE streaming variant of /api/script/refine. Same event contract
    as /api/script/stream (without the intent phase)."""
    import asyncio
    import json

    async def event_gen():
        try:
            llm = _maybe_switch(req.llm_provider, req.llm_model) or _state.get()
            queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _run():
                try:
                    for ev, _result in refine_script_stream(
                        req.original_sql, req.feedback, llm
                    ):
                        loop.call_soon_threadsafe(queue.put_nowait, ev)
                except Exception as e:
                    loop.call_soon_threadsafe(
                        queue.put_nowait, {"type": "error", "error": str(e)}
                    )
                finally:
                    loop.call_soon_threadsafe(queue.put_nowait, None)

            threading.Thread(target=_run, daemon=True).start()

            while True:
                ev = await queue.get()
                if ev is None:
                    break
                t = ev.get("type")
                if t == "phase":
                    yield {"event": "phase", "data": json.dumps(ev, ensure_ascii=False)}
                elif t == "think":
                    yield {"event": "think", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "content":
                    yield {"event": "content", "data": json.dumps({"text": ev.get("text", "")}, ensure_ascii=False)}
                elif t == "final":
                    yield {"event": "final", "data": json.dumps(ev.get("result", {}), ensure_ascii=False, default=str)}
                elif t == "error":
                    yield {"event": "error", "data": json.dumps({"error": ev.get("error", "")}, ensure_ascii=False)}
        except Exception as e:
            log.exception("Script refine stream failed")
            yield {"event": "error", "data": json.dumps({"error": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_gen())


@router.post("/sql/execute")
def execute_sql(req: ExecuteSQLRequest):
    safety = check_sql_safety(req.sql)
    if not safety.ok:
        return {"success": False, "error": safety.reason, "statement_type": safety.statement_type}
    db = get_database()
    try:
        if safety.statement_type == "SELECT":
            cols, rows = db.fetch_rows(req.sql, max_rows=req.max_rows or get_settings().database.max_rows)
            return {"success": True, "statement_type": "SELECT", "columns": cols, "rows": rows}
        else:
            affected = db.execute(req.sql)
            return {"success": True, "statement_type": safety.statement_type, "affected_rows": affected}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/sql/format")
def format_sql_endpoint(req: FormatSQLRequest):
    try:
        formatted = format_sql(req.sql, dialect=req.dialect)
        violations = lint_sql(req.sql, dialect=req.dialect)
        return {"success": True, "formatted": formatted, "violations": violations}
    except Exception as e:
        return {"success": False, "error": str(e), "formatted": req.sql, "violations": []}


@router.post("/sql/lint")
def lint_sql_endpoint(req: FormatSQLRequest):
    return {"success": True, "violations": lint_sql(req.sql, dialect=req.dialect)}


@router.post("/export/sql")
def export_sql(payload: dict):
    from backend.output.exporter import export_to_file

    content = payload.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="content is required")
    try:
        return export_to_file(content=content, file_format="sql")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export/csv")
def export_csv(payload: dict):
    from backend.output.exporter import export_to_file

    rows = payload.get("rows", [])
    cols = payload.get("columns", [])
    if not rows or not cols:
        raise HTTPException(status_code=400, detail="columns and rows are required")
    import pandas as pd

    df = pd.DataFrame(rows, columns=cols)
    try:
        return export_to_file(df=df, file_format="csv")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/reload")
def config_reload():
    try:
        reload_settings()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/settings")
def get_persisted_settings():
    """Return the user-persisted settings (DB + LLM + UI). Sensitive keys
    (api_key / custom_api_key) are masked."""
    from backend.data.user_settings import get_all

    raw = get_all()
    llm = raw.get("llm") or {}
    db = raw.get("db") or {}
    ui = raw.get("ui") or {}
    masked_llm = dict(llm) if llm else None
    if masked_llm and masked_llm.get("custom_api_key"):
        masked_llm["custom_api_key"] = "***"
    if masked_llm and masked_llm.get("api_key"):
        masked_llm["api_key"] = "***"
    return {
        "llm": masked_llm,
        "db": db,
        "ui": ui,
        "has_persisted": bool(raw),
    }


@router.post("/settings/ui")
def set_ui_pref(payload: dict):
    """Set a UI preference key, e.g. {"show_thinking": true}."""
    from backend.data.user_settings import set_ui_pref

    key = payload.get("key")
    value = payload.get("value")
    if not isinstance(key, str) or not key:
        raise HTTPException(status_code=400, detail="key must be a non-empty string")
    set_ui_pref(key, value)
    return {"ok": True, "key": key, "value": value}


@router.post("/settings/reset")
def reset_persisted_settings():
    """Wipe user_settings.json. Does NOT change the in-memory LLM/DB —
    they keep running until the user changes them. Useful for debugging."""
    from backend.data.user_settings import reset

    reset()
    return {"ok": True}


# ---- helpers ----------------------------------------------------------------


def _maybe_switch(provider: Optional[str], model: Optional[str], **kwargs):
    """If provider differs from current, switch and return the new client."""
    if not provider:
        return None
    if provider == _state.provider and (not model or model == _state.model) and not kwargs:
        return None
    _state.switch(provider, model, **kwargs)
    return _state.get()
