"""Schema introspection.

Produces a `SchemaInfo` describing all tables/columns/keys/sample rows in the
current database. The output is JSON-serializable and serves as LLM context.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import inspect, text

from backend.data.connector import Database, get_database
from backend.utils import DBError, get_logger

log = get_logger(__name__)


@dataclass
class TableInfo:
    name: str
    columns: list[dict] = field(default_factory=list)   # [{"name", "type", "nullable", "pk", "default", "comment"}]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)
    row_count: int = 0
    sample: list[dict] = field(default_factory=list)
    comment: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "columns": self.columns,
            "primary_key": self.primary_key,
            "foreign_keys": self.foreign_keys,
            "row_count": self.row_count,
            "sample": self.sample,
            "comment": self.comment,
        }

    def schema_text(self) -> str:
        """Compact text representation for LLM context."""
        col_lines = []
        for c in self.columns:
            marks = []
            if c.get("pk"):
                marks.append("PK")
            if not c.get("nullable", True):
                marks.append("NOT NULL")
            mark_str = f" [{', '.join(marks)}]" if marks else ""
            col_lines.append(f"  - {c['name']}: {c['type']}{mark_str}")
        cols_block = "\n".join(col_lines) if col_lines else "  (no columns)"
        sample_block = ""
        if self.sample:
            sample_block = "\n  sample rows:\n" + "\n".join(
                "    " + str(r) for r in self.sample[:3]
            )
        return f"Table: {self.name}{(' -- ' + self.comment) if self.comment else ''}\n{cols_block}{sample_block}"


@dataclass
class SchemaInfo:
    database: str
    dialect: str
    tables: list[TableInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "database": self.database,
            "dialect": self.dialect,
            "tables": [t.to_dict() for t in self.tables],
        }

    def schema_text(self) -> str:
        """Full schema as a single string for LLM context."""
        head = f"Database: {self.database} (dialect: {self.dialect})"
        body = "\n\n".join(t.schema_text() for t in self.tables)
        return f"{head}\n\n{body}" if self.tables else f"{head}\n(no tables)"

    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]


def introspect_schema(db: Optional[Database] = None, sample_rows: int = 3) -> SchemaInfo:
    """Introspect the current (or given) database."""
    db = db or get_database()
    try:
        insp = inspect(db.engine)
    except Exception as e:
        raise DBError(f"Cannot inspect database: {e}")

    schema = SchemaInfo(database=db.url, dialect=db.dialect)
    try:
        table_names = insp.get_table_names()
    except Exception as e:
        raise DBError(f"Failed to list tables: {e}")

    for tbl in table_names:
        t = TableInfo(name=tbl)
        try:
            cols = insp.get_columns(tbl)
            t.columns = [
                {
                    "name": c["name"],
                    "type": str(c.get("type", "")),
                    "nullable": bool(c.get("nullable", True)),
                    "default": str(c.get("default")) if c.get("default") is not None else None,
                }
                for c in cols
            ]
        except Exception as e:
            log.warning(f"Failed to read columns of {tbl}: {e}")

        try:
            pk = insp.get_pk_constraint(tbl)
            t.primary_key = list(pk.get("constrained_columns", []) or [])
            t.columns = [{**c, "pk": c["name"] in t.primary_key} for c in t.columns]
        except Exception:
            pass

        try:
            fks = insp.get_foreign_keys(tbl)
            t.foreign_keys = [
                {
                    "columns": fk.get("constrained_columns", []),
                    "referred_table": fk.get("referred_table"),
                    "referred_columns": fk.get("referred_columns", []),
                }
                for fk in fks
            ]
        except Exception:
            pass

        try:
            t.comment = (insp.get_table_comment(tbl) or {}).get("text") or ""
        except Exception:
            pass

        # row count (cheap on sqlite, may be slow on large tables)
        try:
            with db.connect() as conn:
                r = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
                t.row_count = int(r or 0)
        except Exception:
            t.row_count = 0

        # sample rows
        try:
            with db.connect() as conn:
                df = __import__("pandas").read_sql_query(
                    text(f'SELECT * FROM "{tbl}" LIMIT {int(sample_rows)}'), conn
                )
                t.sample = [
                    {k: (None if (v is None or (isinstance(v, float) and v != v)) else str(v)) for k, v in row.items()}
                    for row in df.to_dict(orient="records")
                ]
        except Exception as e:
            log.debug(f"Sample rows for {tbl} failed: {e}")

        schema.tables.append(t)

    return schema
