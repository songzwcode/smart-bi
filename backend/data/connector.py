"""SQLAlchemy-based multi-database connector.

Supports SQLite (default), MySQL, PostgreSQL via URL string.

URL examples:
    sqlite:///path/to/file.db
    sqlite:///:memory:
    mysql+pymysql://user:pass@host:3306/dbname
    postgresql+psycopg2://user:pass@host:5432/dbname
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import urlparse

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from backend.config import get_settings
from backend.utils import DBError, get_logger

log = get_logger(__name__)


def normalize_url(url: str) -> str:
    """Expand ~ in sqlite file paths."""
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///") :]
        if path and not path.startswith(":") and not Path(path).is_absolute():
            expanded = Path(path).expanduser()
            if expanded != Path(path):
                return f"sqlite:///{expanded}"
    return url


def dialect_of(url: str) -> str:
    """Return 'sqlite' | 'mysql' | 'postgres' | 'other'."""
    scheme = urlparse(url).scheme.split("+")[0]
    if scheme in ("sqlite", "mysql", "postgres", "postgresql"):
        return "postgresql" if scheme == "postgres" else scheme
    return "other"


class Database:
    """Thin wrapper around a SQLAlchemy Engine with safety + caching hooks."""

    def __init__(self, url: str, *, readonly: bool = True, query_timeout: int = 30):
        self.url = normalize_url(url)
        self.readonly = readonly
        self.query_timeout = query_timeout
        self._engine: Engine = self._make_engine()

    def _make_engine(self) -> Engine:
        connect_args: dict[str, Any] = {}
        if self.url.startswith("sqlite"):
            # ensure parent dir exists for sqlite file urls
            if self.url.startswith("sqlite:///"):
                p = self.url[len("sqlite:///") :]
                if p and not p.startswith(":"):
                    Path(p).expanduser().parent.mkdir(parents=True, exist_ok=True)
            connect_args["check_same_thread"] = False
        try:
            engine = create_engine(
                self.url,
                connect_args=connect_args,
                pool_pre_ping=True,
                future=True,
            )
        except SQLAlchemyError as e:
            raise DBError(f"Failed to create engine: {e}", hint=f"Check connection URL: {self.url}")
        return engine

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def dialect(self) -> str:
        return dialect_of(self.url)

    def test_connection(self) -> dict:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"ok": True, "url": self.url, "dialect": self.dialect}
        except Exception as e:
            return {"ok": False, "url": self.url, "dialect": self.dialect, "error": str(e)}

    @contextmanager
    def connect(self):
        try:
            with self._engine.connect() as conn:
                yield conn
        except SQLAlchemyError as e:
            raise DBError(f"DB connection error: {e}")

    def execute(self, sql: str, params: Optional[dict] = None) -> int:
        """Execute a write statement, return affected row count."""
        with self.connect() as conn:
            trans = conn.begin()
            try:
                result = conn.execute(text(sql), params or {})
                trans.commit()
                return result.rowcount or 0
            except Exception:
                trans.rollback()
                raise

    def fetch_df(self, sql: str, params: Optional[dict] = None) -> pd.DataFrame:
        """Run a SELECT and return a pandas DataFrame."""
        try:
            with self.connect() as conn:
                df = pd.read_sql_query(text(sql), conn, params=params or {})
            return df
        except Exception as e:
            raise DBError(f"Query failed: {e}", hint="Check SQL syntax or table/column names.")

    def fetch_rows(self, sql: str, params: Optional[dict] = None, max_rows: int = 1000) -> tuple[list[str], list[tuple]]:
        """Run a SELECT and return (columns, rows). Caps to max_rows."""
        df = self.fetch_df(sql, params)
        if len(df) > max_rows:
            df = df.head(max_rows)
        cols = [str(c) for c in df.columns]
        # Convert NaN/NaT to None for JSON safety
        df = df.astype(object).where(pd.notnull(df), None)
        rows = [tuple(r) for r in df.itertuples(index=False, name=None)]
        return cols, rows

    def dispose(self) -> None:
        try:
            self._engine.dispose()
        except Exception:
            pass


# ---- global singleton with thread-safe switching ----------------------------


_lock = threading.RLock()
_current: Optional[Database] = None


def get_database() -> Database:
    global _current
    with _lock:
        if _current is None:
            s = get_settings()
            url = s.database.default_url
            # If the user previously persisted a connection, honor it.
            try:
                from backend.data.user_settings import get_db
                saved = get_db()
                if saved and saved.get("db_type"):
                    from backend.api.schemas import ConnectionConfig
                    cfg = ConnectionConfig(**saved)
                    url = cfg.to_url()
                    log.info(f"Restored DB from user settings: {url}")
            except Exception as e:
                log.warning(f"Failed to restore saved DB, using default: {e}")
            _current = Database(
                url,
                readonly=s.database.readonly_by_default,
                query_timeout=s.database.query_timeout_seconds,
            )
        return _current


def switch_database(url: str, *, readonly: Optional[bool] = None) -> Database:
    global _current
    with _lock:
        s = get_settings()
        if readonly is None:
            readonly = s.database.readonly_by_default
        # dispose previous
        if _current is not None:
            try:
                _current.dispose()
            except Exception:
                pass
        _current = Database(url, readonly=readonly, query_timeout=s.database.query_timeout_seconds)
        return _current
