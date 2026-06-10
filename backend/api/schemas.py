"""Pydantic request/response schemas."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---- query (NL → data) ------------------------------------------------------


class QueryRequest(BaseModel):
    question: str
    chart_type: Optional[str] = None  # bar | line | pie | scatter | area | None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class QueryResponse(BaseModel):
    success: bool = True
    question: str
    intent: dict
    plan: dict
    steps: list[dict]
    final_sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list] = Field(default_factory=list)
    chart: Optional[dict] = None
    chart_type: Optional[str] = None
    chart_auto: bool = False
    elapsed_ms: int = 0
    llm_model: str = ""
    error: Optional[str] = None


# ---- script (NL → SQL/SP) ---------------------------------------------------


class ScriptRequest(BaseModel):
    requirement: str
    script_subtype: Optional[str] = None  # query | dml | procedure
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class ScriptRefineRequest(BaseModel):
    original_sql: str
    feedback: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None


class ScriptResponse(BaseModel):
    success: bool = True
    requirement: str
    code: str
    language: str
    script_subtype: str
    intent: Optional[dict] = None
    elapsed_ms: int = 0
    error: Optional[str] = None


# ---- direct SQL execution & formatting --------------------------------------


class ExecuteSQLRequest(BaseModel):
    sql: str
    max_rows: Optional[int] = None


class FormatSQLRequest(BaseModel):
    sql: str
    dialect: Optional[str] = None


# ---- connection & LLM config ------------------------------------------------


class ConnectionConfig(BaseModel):
    db_type: str = "sqlite"   # sqlite | mysql | postgres
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    file_path: Optional[str] = None   # sqlite only

    def to_url(self) -> str:
        if self.db_type == "sqlite":
            p = self.file_path or ":memory:"
            if not p.startswith("/") and p != ":memory:":
                from pathlib import Path
                p = str(Path(p).expanduser())
            return f"sqlite:///{p}"
        if self.db_type == "mysql":
            return (
                f"mysql+pymysql://{self.user}:{self.password}@"
                f"{self.host}:{self.port or 3306}/{self.database}"
            )
        if self.db_type in ("postgres", "postgresql"):
            return (
                f"postgresql+psycopg2://{self.user}:{self.password}@"
                f"{self.host}:{self.port or 5432}/{self.database}"
            )
        raise ValueError(f"Unsupported db_type: {self.db_type}")


class ConnectionTestRequest(BaseModel):
    config: ConnectionConfig
    readonly: bool = True


class LLMSwitchRequest(BaseModel):
    provider: str   # ollama | openai | anthropic | custom
    model: Optional[str] = None
    ollama_url: Optional[str] = None
    api_key: Optional[str] = None
    custom_url: Optional[str] = None


class LLMInfo(BaseModel):
    current_provider: str
    current_model: str
    available: list[dict] = Field(default_factory=list)


# ---- schema & health --------------------------------------------------------


class SchemaResponse(BaseModel):
    database: str
    dialect: str
    tables: list[dict]
    schema_text: str
    reindexed: bool = False


class HealthResponse(BaseModel):
    ok: bool = True
    app: str
    version: str
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    db_url: str
    db_dialect: str
