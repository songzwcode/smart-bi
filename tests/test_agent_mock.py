"""End-to-end agent test with a mock LLM.

Validates the Query Mode flow: intent → planner → SQL gen → execute → render.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from backend.agent.sql_agent import run_query
from backend.config import get_settings
from backend.data.connector import Database, switch_database
from backend.llm.base import LLMClient, LLMResponse, Message


class MockLLM(LLMClient):
    """A scripted LLM that returns canned responses in order."""

    provider = "mock"

    def __init__(self, responses: list[str]):
        super().__init__(model="mock-model")
        self._responses = list(responses)
        self._calls: list[list[Message]] = []

    def chat(
        self,
        messages: list[Message],
        *,
        tools=None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        self._calls.append(messages)
        if not self._responses:
            return LLMResponse(content="SELECT 1", model="mock-model")
        text = self._responses.pop(0)
        return LLMResponse(content=text, model="mock-model")


@pytest.fixture
def temp_db(tmp_path: Path):
    import sqlite3

    p = tmp_path / "agent_test.db"
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, region TEXT)")
    c.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, amount REAL)")
    c.execute("INSERT INTO customers (name, region) VALUES ('alice', 'east'), ('bob', 'west')")
    c.execute("INSERT INTO orders (customer_id, amount) VALUES (1, 100), (1, 200), (2, 50)")
    c.commit()
    c.close()

    # override settings default url temporarily
    s = get_settings()
    original = s.database.default_url
    s.database.default_url = f"sqlite:///{p}"
    switch_database(s.database.default_url, readonly=True)
    yield f"sqlite:///{p}"
    s.database.default_url = original


def test_run_query_basic(temp_db: str):
    """Full Query Mode run with a mock LLM that returns a known SQL."""
    # Disable RAG to avoid chromadb requirement
    s = get_settings()
    s.agent.enable_schema_rag = False
    s.agent.enable_planner = False

    # Mock LLM returns: 1) intent JSON  2) SQL
    llm = MockLLM(
        [
            '{"intent": "query_data", "confidence": 0.95, "params": {}, "reasoning": "test"}',
            "SELECT name, SUM(amount) AS total FROM customers c JOIN orders o ON c.id=o.customer_id GROUP BY name ORDER BY total DESC",
        ]
    )

    result = run_query("show me sales by customer", llm)

    assert result.intent.intent == "query_data"
    assert result.final_sql != ""
    assert "SELECT" in result.final_sql.upper()
    assert len(result.final_rows) == 2
    # alice had 300, bob had 50
    rows_by_name = {r[0]: r[1] for r in result.final_rows}
    assert rows_by_name["alice"] == 300
    assert rows_by_name["bob"] == 50


def test_run_query_empty_result(temp_db: str):
    """Mock LLM returns SQL that yields no rows."""
    s = get_settings()
    s.agent.enable_schema_rag = False
    s.agent.enable_planner = False

    llm = MockLLM(
        [
            '{"intent": "query_data", "confidence": 0.9, "params": {}}',
            "SELECT * FROM customers WHERE name = 'nobody'",
        ]
    )
    result = run_query("nobody", llm)
    assert result.final_rows == []


def test_run_query_self_correction(temp_db: str):
    """Mock LLM returns invalid SQL first, then corrected SQL."""
    s = get_settings()
    s.agent.enable_schema_rag = False
    s.agent.enable_planner = False
    s.agent.max_self_correct_rounds = 2

    # 1st call: bad SQL. 2nd call: intent. 3rd call: good SQL.
    # Note: intent is called separately by classify_intent — but we provide
    # enough responses to cover all LLM calls in the pipeline.
    llm = MockLLM(
        [
            # intent
            '{"intent": "query_data", "confidence": 0.9, "params": {}}',
            # initial bad SQL
            "SELECT * FROM nonexistent_table",
            # self-corrected SQL
            "SELECT name FROM customers ORDER BY name",
        ]
    )
    result = run_query("list customer names", llm)
    # Should have recovered via self-correction
    assert result.final_sql != ""
    assert "customers" in result.final_sql.lower()
    assert len(result.final_rows) == 2
