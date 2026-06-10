"""Tests for backend.data.introspect."""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.data.connector import Database
from backend.data.introspect import introspect_schema


@pytest.fixture
def sample_db(tmp_path: Path) -> Database:
    import sqlite3

    p = tmp_path / "test.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT)")
    c.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL)")
    c.execute("INSERT INTO users (name, email) VALUES ('alice', 'a@x.com'), ('bob', 'b@x.com')")
    c.execute("INSERT INTO orders (user_id, total) VALUES (1, 100.5), (1, 200), (2, 50)")
    c.commit()
    c.close()
    return Database(f"sqlite:///{p}")


def test_introspect_basic(sample_db: Database):
    info = introspect_schema(sample_db)
    assert info.dialect == "sqlite"
    assert set(info.table_names()) == {"users", "orders"}


def test_introspect_columns(sample_db: Database):
    info = introspect_schema(sample_db)
    users = next(t for t in info.tables if t.name == "users")
    col_names = [c["name"] for c in users.columns]
    assert "id" in col_names
    assert "name" in col_names
    assert "email" in col_names


def test_introspect_primary_key(sample_db: Database):
    info = introspect_schema(sample_db)
    users = next(t for t in info.tables if t.name == "users")
    assert users.primary_key == ["id"]


def test_introspect_row_count(sample_db: Database):
    info = introspect_schema(sample_db)
    users = next(t for t in info.tables if t.name == "users")
    orders = next(t for t in info.tables if t.name == "orders")
    assert users.row_count == 2
    assert orders.row_count == 3


def test_introspect_schema_text(sample_db: Database):
    info = introspect_schema(sample_db)
    text = info.schema_text()
    assert "users" in text
    assert "orders" in text
    assert "id:" in text or "id" in text


def test_introspect_sample_rows(sample_db: Database):
    info = introspect_schema(sample_db)
    users = next(t for t in info.tables if t.name == "users")
    assert len(users.sample) > 0
    assert "name" in users.sample[0]
