"""SQL formatting & linting via sqlfluff."""
from __future__ import annotations

from typing import Optional

from backend.config import get_settings
from backend.utils import get_logger

log = get_logger(__name__)


_DIALECT_MAP = {
    "sqlite": "ansi",
    "mysql": "mysql",
    "postgres": "postgres",
    "postgresql": "postgres",
    "ansi": "ansi",
}


def _to_sqlfluff_dialect(dialect: str) -> str:
    return _DIALECT_MAP.get((dialect or "ansi").lower(), "ansi")


def format_sql(sql: str, dialect: Optional[str] = None) -> str:
    """Format SQL using sqlfluff. Falls back to original on error."""
    if not sql or not sql.strip():
        return sql
    s = get_settings()
    d = dialect or s.output.sql_dialect_default
    sf_dialect = _to_sqlfluff_dialect(d)
    try:
        from sqlfluff.core import Linter, FluffConfig

        config = FluffConfig(overrides={"dialect": sf_dialect, "rules": None})
        linter = Linter(config=config)
        result = linter.lint_string(sql, fname=f"<{sf_dialect}>")
        if result.tree:
            from sqlfluff.core import Formatter

            formatter = Formatter(config=config)
            formatted = formatter.format_string(result.tree).strip()
            return formatted
    except Exception as e:
        log.warning(f"sqlfluff format failed: {e}")
    return sql


def lint_sql(sql: str, dialect: Optional[str] = None) -> list[dict]:
    """Return a list of lint violations. Empty list on success/error."""
    if not sql or not sql.strip():
        return []
    s = get_settings()
    d = dialect or s.output.sql_dialect_default
    sf_dialect = _to_sqlfluff_dialect(d)
    try:
        from sqlfluff.core import Linter, FluffConfig

        config = FluffConfig(overrides={"dialect": sf_dialect})
        linter = Linter(config=config)
        result = linter.lint_string(sql, fname=f"<{sf_dialect}>")
        violations = []
        for v in result.violations:
            violations.append(
                {
                    "rule": getattr(v, "rule_code", lambda: "")() if callable(getattr(v, "rule_code", None)) else str(getattr(v, "rule_code", "")),
                    "line": getattr(v, "line_no", 0),
                    "description": getattr(v, "description", ""),
                    "warning": bool(getattr(v, "is_warning", False)),
                }
            )
        return violations
    except Exception as e:
        log.warning(f"sqlfluff lint failed: {e}")
        return []
