"""Tests for backend.data.safety."""
from __future__ import annotations

import pytest

from backend.data.safety import check_sql_safety


class TestCheckSQLSafety:
    def test_select_allowed(self):
        r = check_sql_safety("SELECT * FROM users")
        assert r.ok
        assert r.statement_type == "SELECT"

    def test_select_with_join(self):
        r = check_sql_safety(
            "SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id=o.user_id GROUP BY u.name"
        )
        assert r.ok
        assert r.statement_type == "SELECT"

    def test_drop_rejected(self):
        r = check_sql_safety("DROP TABLE users")
        assert not r.ok
        assert "DROP" in r.reason

    def test_truncate_rejected(self):
        r = check_sql_safety("TRUNCATE TABLE logs")
        assert not r.ok
        assert "TRUNCATE" in r.reason

    def test_alter_rejected(self):
        r = check_sql_safety("ALTER TABLE users ADD COLUMN foo INT")
        assert not r.ok

    def test_grant_rejected(self):
        r = check_sql_safety("GRANT ALL ON users TO public")
        assert not r.ok

    def test_delete_rejected_by_default(self):
        r = check_sql_safety("DELETE FROM orders WHERE id=1")
        assert not r.ok
        assert "DELETE" in r.reason

    def test_update_rejected_by_default(self):
        r = check_sql_safety("UPDATE users SET name='x' WHERE id=1")
        assert not r.ok
        assert "UPDATE" in r.reason

    def test_insert_rejected_by_default(self):
        r = check_sql_safety("INSERT INTO users (name) VALUES ('foo')")
        assert not r.ok

    def test_empty_sql_rejected(self):
        r = check_sql_safety("   ")
        assert not r.ok
        assert "empty" in r.reason.lower()

    def test_keyword_in_identifier_is_not_matched(self):
        # `\bDROP\b` does NOT match `drop_id` because `_` is a word character.
        # This is correct — we want to allow identifiers containing "drop".
        r = check_sql_safety("SELECT id AS drop_id FROM users")
        assert r.ok
        assert r.statement_type == "SELECT"

    def test_keyword_as_standalone_word_is_blocked(self):
        # Bare "DROP" (with word boundary) IS caught.
        r = check_sql_safety("SELECT * FROM users; DROP TABLE logs")
        assert not r.ok
        assert "DROP" in r.reason

    def test_create_table_rejected(self):
        r = check_sql_safety("CREATE TABLE foo (id INT)")
        assert not r.ok
        assert r.statement_type == "DDL"

    def test_create_user_rejected(self):
        r = check_sql_safety("CREATE USER hacker WITH PASSWORD 'x'")
        assert not r.ok


class TestSQLGlotParsing:
    def test_ansi_default_dialect(self):
        """Default config uses 'ansi' — sqlglot should auto-detect, not error."""
        r = check_sql_safety("SELECT NOW()")
        assert r.ok

    def test_mysql_specific_syntax(self):
        # Backticks are MySQL-specific; default dialect='ansi' won't parse them.
        # This is expected — the user must switch dialect for MySQL syntax.
        r = check_sql_safety("SELECT `id` FROM `users`")
        # Without MySQL dialect set, parsing fails — this is the expected
        # behavior; callers should set dialect='mysql' to enable.
        assert not r.ok
        assert "parse error" in r.reason.lower()
