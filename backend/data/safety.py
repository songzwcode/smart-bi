"""SQL safety checks.

Lightweight keyword-based guard. For production, also use a read-only DB user
and SQLAlchemy parameterised queries (which the agent does).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from backend.config import get_settings
from backend.utils import SQLError

# Keywords we always block (case-insensitive)
_ALWAYS_BLOCK = ["DROP", "TRUNCATE", "ALTER", "GRANT", "REVOKE", "CREATE USER", "CREATE ROLE"]


# Map our config dialect -> sqlglot dialect (sqlglot uses "ansi" as default
# when no dialect is detected, but doesn't accept "ansi" as a `read=` value)
_DIALECT_FOR_SQLGLOT = {
    "ansi": None,             # let sqlglot auto-detect
    "sqlite": "sqlite",
    "mysql": "mysql",
    "postgres": "postgres",
    "postgresql": "postgres",
}


@dataclass
class SQLSafetyResult:
    ok: bool
    reason: str = ""
    statement_type: str = ""   # SELECT | INSERT | UPDATE | DELETE | DDL | OTHER


def _normalise(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def check_sql_safety(sql: str) -> SQLSafetyResult:
    """Validate that the SQL is safe to run given the current settings.

    Rules:
      - If `database.readonly_by_default`, only SELECT is allowed.
      - DELETE/UPDATE without WHERE is blocked.
      - `database.dangerous_keywords` are always blocked.
    """
    s = get_settings()
    cleaned = _normalise(sql)
    if not cleaned:
        return SQLSafetyResult(ok=False, reason="empty SQL")

    upper = cleaned.upper()

    # 1. Always block DDL-class keywords
    for kw in s.database.dangerous_keywords + _ALWAYS_BLOCK:
        if re.search(rf"\b{re.escape(kw)}\b", upper):
            return SQLSafetyResult(ok=False, reason=f"blocked keyword: {kw}", statement_type="DDL")

    # 2. Parse with sqlglot to detect statement type
    sqlglot_dialect = _DIALECT_FOR_SQLGLOT.get(s.output.sql_dialect_default.lower())
    try:
        if sqlglot_dialect:
            parsed = sqlglot.parse_one(cleaned, read=sqlglot_dialect)
        else:
            parsed = sqlglot.parse_one(cleaned)
    except Exception as e:
        return SQLSafetyResult(ok=False, reason=f"parse error: {e}")

    stmt_type = "OTHER"
    if isinstance(parsed, exp.Select):
        stmt_type = "SELECT"
    elif isinstance(parsed, exp.Insert):
        stmt_type = "INSERT"
    elif isinstance(parsed, exp.Update):
        stmt_type = "UPDATE"
    elif isinstance(parsed, exp.Delete):
        stmt_type = "DELETE"
    elif isinstance(parsed, (exp.Create, exp.Drop, exp.Alter)):
        stmt_type = "DDL"
    else:
        stmt_type = type(parsed).__name__.upper()

    # 3. DML whitelist
    if stmt_type in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        if stmt_type not in s.database.allowed_dml:
            return SQLSafetyResult(
                ok=False,
                reason=f"statement type {stmt_type} not in allowed_dml={s.database.allowed_dml}",
                statement_type=stmt_type,
            )
    elif stmt_type == "DDL":
        return SQLSafetyResult(ok=False, reason="DDL not allowed", statement_type=stmt_type)

    # 4. UPDATE/DELETE must have a WHERE
    if stmt_type in ("UPDATE", "DELETE") and not parsed.args.get("where"):
        return SQLSafetyResult(
            ok=False,
            reason=f"{stmt_type} without WHERE is forbidden",
            statement_type=stmt_type,
        )

    return SQLSafetyResult(ok=True, statement_type=stmt_type)


def assert_safe(sql: str) -> SQLSafetyResult:
    res = check_sql_safety(sql)
    if not res.ok:
        raise SQLError(res.reason, hint="Adjust the SQL or relax safety settings.", sql=sql)
    return res
