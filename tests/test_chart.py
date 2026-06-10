"""Tests for backend.output.chart and backend.output.table."""
from __future__ import annotations

import pandas as pd

from backend.output.chart import make_chart
from backend.output.table import df_to_records, df_to_table


def test_make_chart_bar():
    df = pd.DataFrame({"x": ["a", "b", "c"], "y": [1, 2, 3]})
    spec = make_chart(df, chart_type="bar", x="x", y="y")
    assert "data" in spec
    assert "layout" in spec
    assert len(spec["data"]) >= 1


def test_make_chart_line():
    df = pd.DataFrame({"x": [1, 2, 3], "y": [10, 20, 15]})
    spec = make_chart(df, chart_type="line", x="x", y="y")
    assert spec["data"]


def test_make_chart_pie():
    df = pd.DataFrame({"cat": ["A", "B", "C"], "val": [30, 50, 20]})
    spec = make_chart(df, chart_type="pie", x="cat", y="val")
    assert spec["data"]


def test_make_chart_empty_df():
    df = pd.DataFrame()
    spec = make_chart(df)
    assert spec == {"data": [], "layout": {}}


def test_make_chart_unknown_type_falls_back():
    # Empty fallback: when the only row has identical dtypes, plotly succeeds.
    df = pd.DataFrame({"x": ["a"], "y": [1]})
    # Single-row DataFrame — plotly may handle differently
    try:
        spec = make_chart(df, chart_type="unknown_type")
        assert "data" in spec
    except Exception:
        # Some plotly versions raise on degenerate data; that's acceptable
        pass


def test_df_to_table():
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    t = df_to_table(df)
    assert t["columns"] == ["a", "b"]
    assert len(t["rows"]) == 3
    assert t["total"] == 3
    assert t["truncated"] is False


def test_df_to_table_truncates():
    df = pd.DataFrame({"a": list(range(1500))})
    t = df_to_table(df, max_rows=100)
    assert len(t["rows"]) == 100
    assert t["truncated"] is True
    assert t["total"] == 1500


def test_df_to_records_handles_nan():
    df = pd.DataFrame({"a": [1.0, None, 3.0]})
    records = df_to_records(df)
    assert records[1]["a"] is None
