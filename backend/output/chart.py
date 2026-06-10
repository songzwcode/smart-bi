"""Plotly chart generation.

`make_chart()` returns a JSON-serialisable dict that the frontend can render
directly via plotly.js.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

chart_types = ["bar", "line", "pie", "scatter", "area"]


def make_chart(
    df: pd.DataFrame,
    *,
    chart_type: str = "bar",
    x: Optional[str] = None,
    y: Optional[str] = None,
    title: Optional[str] = None,
) -> dict:
    """Build a Plotly chart from a DataFrame and return its JSON spec."""
    if df is None or df.empty:
        return {"data": [], "layout": {}}
    chart_type = (chart_type or "bar").lower()
    if chart_type not in chart_types:
        chart_type = "bar"

    common = {"title": title or ""}
    try:
        if chart_type == "bar":
            fig = px.bar(df, x=x, y=y, **common)
        elif chart_type == "line":
            fig = px.line(df, x=x, y=y, **common)
        elif chart_type == "pie":
            fig = px.pie(df, names=x, values=y, **common)
        elif chart_type == "scatter":
            fig = px.scatter(df, x=x, y=y, **common)
        elif chart_type == "area":
            fig = px.area(df, x=x, y=y, **common)
        else:
            fig = go.Figure()
    except Exception:
        # Fallback to plain bar
        fig = px.bar(df, x=x, y=y, **common)

    fig.update_layout(margin=dict(l=20, r=20, t=40, b=20), height=360)
    # Return a JSON spec; the frontend uses Plotly.react
    return fig.to_plotly_json()
