"""Configuration loader.

Reads `config.yaml` and overlays env vars / `.env`.
Exposes a singleton `settings` (a `Settings` instance).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from backend.utils import ConfigError, get_logger

log = get_logger(__name__)

# Repo root = parent of `backend/`
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"
ENV_PATH = ROOT_DIR / ".env"


# ---- nested config models ---------------------------------------------------


class OllamaConfig(BaseModel):
    base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5-coder:14b"


class OpenAIConfig(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o"
    api_key_env: str = "OPENAI_API_KEY"


class AnthropicConfig(BaseModel):
    base_model: str = "claude-3-5-sonnet-20241022"
    api_key_env: str = "ANTHROPIC_API_KEY"


class CustomConfig(BaseModel):
    """OpenAI-compatible HTTP LLM endpoint (vLLM, llama.cpp, LiteLLM, OpenRouter, etc.)."""
    base_url: str = ""
    default_model: str = ""
    api_key: str = ""
    api_key_env: str = "CUSTOM_LLM_API_KEY"


class LLMProvidersConfig(BaseModel):
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)
    custom: CustomConfig = Field(default_factory=CustomConfig)


class LLMConfig(BaseModel):
    default_provider: str = "ollama"
    providers: LLMProvidersConfig = Field(default_factory=LLMProvidersConfig)


class AgentConfig(BaseModel):
    max_self_correct_rounds: int = 2
    max_plan_steps: int = 6
    enable_planner: bool = True
    enable_schema_rag: bool = True
    schema_rag_top_k: int = 5
    enable_few_shot: bool = True
    few_shot_count: int = 5


class DatabaseConfig(BaseModel):
    default_url: str = "sqlite:///examples/sample.db"
    readonly_by_default: bool = True
    dangerous_keywords: list[str] = [
        "DROP",
        "TRUNCATE",
        "ALTER",
        "GRANT",
        "REVOKE",
        "CREATE USER",
    ]
    allowed_dml: list[str] = ["SELECT"]
    query_timeout_seconds: int = 30
    max_rows: int = 1000


class OutputConfig(BaseModel):
    chart_default_type: str = "bar"
    chart_theme: str = "plotly_white"
    sql_dialect_default: str = "ansi"


class PathsConfig(BaseModel):
    static_dir: str = "backend/static"
    prompts_dir: str = "backend/agent/prompts"
    data_dir: str = "~/.smart-bi"
    export_dir: str = "~/Documents/SmartBI"


class AppConfig(BaseModel):
    name: str = "Smart BI"
    version: str = "0.1.0"
    debug: bool = False
    host: str = "127.0.0.1"
    port_range: list[int] = [17890, 17999]


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "~/.smart-bi/logs/app.log"
    rotation: str = "10 MB"
    retention: str = "7 days"


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    def abs_path(self, p: str) -> Path:
        """Expand ~ and resolve relative to repo root."""
        expanded = Path(p).expanduser()
        if expanded.is_absolute():
            return expanded
        return (ROOT_DIR / expanded).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"config.yaml root must be a mapping, got {type(data)}")
    return data


def _load_settings(config_path: Optional[Path] = None) -> Settings:
    config_path = config_path or DEFAULT_CONFIG_PATH
    # .env is optional
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=False)
    data = _load_yaml(config_path)
    try:
        return Settings(**data)
    except Exception as e:
        raise ConfigError(f"Failed to load config: {e}", hint="Check config.yaml structure.")


# Singleton — lazily initialized.
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _load_settings()
        # configure logger based on settings
        from backend.utils.logger import configure

        configure(
            level=_settings.logging.level,
            file=_settings.logging.file,
            rotation=_settings.logging.rotation,
            retention=_settings.logging.retention,
        )
    return _settings


def reload_settings() -> Settings:
    """Force re-read of config.yaml (e.g. after user edits it)."""
    global _settings
    _settings = None
    return get_settings()


settings = get_settings() if os.getenv("SMART_BI_SKIP_AUTOLOAD") != "1" else None
