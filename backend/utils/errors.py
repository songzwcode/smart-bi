"""Custom exception hierarchy."""
from __future__ import annotations


class AppError(Exception):
    """Base error for Smart BI."""

    def __init__(self, message: str, *, hint: str | None = None, code: str = "app_error"):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.code = code

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "hint": self.hint}


class ConfigError(AppError):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message, hint=hint, code="config_error")


class LLMError(AppError):
    def __init__(self, message: str, hint: str | None = None, provider: str | None = None):
        super().__init__(message, hint=hint, code="llm_error")
        self.provider = provider


class DBError(AppError):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message, hint=hint, code="db_error")


class SQLError(AppError):
    def __init__(self, message: str, hint: str | None = None, sql: str | None = None):
        super().__init__(message, hint=hint, code="sql_error")
        self.sql = sql


class AgentError(AppError):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message, hint=hint, code="agent_error")
