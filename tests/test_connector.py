"""Tests for backend.data.connector (SQLite only — requires no extra drivers)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from backend.data.connector import Database, dialect_of, normalize_url


class TestNormalizeUrl:
    def test_sqlite_passthrough(self):
        assert normalize_url("sqlite:///foo.db") == "sqlite:///foo.db"

    def test_sqlite_in_memory(self):
        assert normalize_url("sqlite:///:memory:") == "sqlite:///:memory:"

    def test_sqlite_expand_user(self):
        if "HOME" in os.environ:
            result = normalize_url("sqlite:///~/test.db")
            assert "~" not in result.split("///")[1]

    def test_mysql_passthrough(self):
        url = "mysql+pymysql://user:pass@host:3306/db"
        assert normalize_url(url) == url


class TestDialectOf:
    def test_sqlite(self):
        assert dialect_of("sqlite:///foo.db") == "sqlite"

    def test_mysql(self):
        assert dialect_of("mysql+pymysql://x@y/z") == "mysql"

    def test_postgres(self):
        assert dialect_of("postgresql+psycopg2://x") == "postgresql"

    def test_postgres_alias(self):
        assert dialect_of("postgres://x") == "postgresql"

    def test_unknown(self):
        assert dialect_of("bigquery://x") == "other"


class TestDatabaseSQLite:
    @pytest.fixture
    def db(self, tmp_path: Path) -> Database:
        path = tmp_path / "test.db"
        # create a simple table
        import sqlite3

        c = sqlite3.connect(path)
        c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        c.execute("INSERT INTO users (name) VALUES ('alice'), ('bob'), ('charlie')")
        c.commit()
        c.close()
        return Database(f"sqlite:///{path}", readonly=False)

    def test_basic_query(self, db: Database):
        cols, rows = db.fetch_rows("SELECT name FROM users ORDER BY id")
        assert cols == ["name"]
        assert rows == [("alice",), ("bob",), ("charlie",)]

    def test_count(self, db: Database):
        cols, rows = db.fetch_rows("SELECT COUNT(*) AS n FROM users")
        assert rows[0][0] == 3

    def test_max_rows_truncates(self, db: Database):
        cols, rows = db.fetch_rows("SELECT * FROM users", max_rows=2)
        assert len(rows) == 2

    def test_execute_dml(self, db: Database):
        affected = db.execute("DELETE FROM users WHERE name = 'alice'")
        assert affected == 1
        cols, rows = db.fetch_rows("SELECT COUNT(*) FROM users")
        assert rows[0][0] == 2

    def test_test_connection(self, db: Database):
        r = db.test_connection()
        assert r["ok"] is True
        assert r["dialect"] == "sqlite"

    def test_fetch_df_returns_dataframe(self, db: Database):
        df = db.fetch_df("SELECT name FROM users")
        assert len(df) == 3
        assert list(df.columns) == ["name"]
