"""Table serialisation for the frontend."""
from __future__ import annotations

from typing import Any

import pandas as pd


def df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a DataFrame to a list of plain dicts with None for NaN."""
    if df is None or df.empty:
        return []
    df = df.astype(object).where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def df_to_table(df: pd.DataFrame, *, max_rows: int = 1000) -> dict:
    """Convert a DataFrame to a JSON-serialisable table structure."""
    if df is None:
        return {"columns": [], "rows": [], "total": 0, "truncated": False}
    total = int(len(df))
    truncated = total > max_rows
    if truncated:
        df = df.head(max_rows)
    cols = [str(c) for c in df.columns]
    df2 = df.astype(object).where(pd.notnull(df), None)
    rows = [list(r) for r in df2.itertuples(index=False, name=None)]
    return {
        "columns": cols,
        "rows": rows,
        "total": total,
        "truncated": truncated,
        "max_rows": max_rows,
    }
