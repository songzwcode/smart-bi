"""Export results to .sql / .csv / .png files."""
from __future__ import annotations

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from backend.config import get_settings
from backend.utils import get_logger

log = get_logger(__name__)


def export_to_file(
    *,
    content: Optional[str] = None,
    df: Optional[pd.DataFrame] = None,
    file_format: str,
    filename: Optional[str] = None,
) -> dict:
    """Save content/df to a file in the export directory.

    Returns: { path, filename, size_bytes, format }
    """
    s = get_settings()
    export_dir = s.abs_path(s.paths.export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_format = (file_format or "").lower().lstrip(".")
    filename = filename or f"smartbi_{ts}.{file_format}"
    if not filename.endswith(f".{file_format}"):
        filename = f"{filename}.{file_format}"
    path = export_dir / filename

    try:
        if file_format == "sql":
            if content is None:
                raise ValueError("SQL export requires `content`")
            path.write_text(content, encoding="utf-8")
        elif file_format == "csv":
            if df is None:
                raise ValueError("CSV export requires `df`")
            df.to_csv(path, index=False, encoding="utf-8")
        elif file_format == "json":
            if df is None:
                raise ValueError("JSON export requires `df`")
            df.to_json(path, orient="records", force_ascii=False, indent=2)
        elif file_format == "png":
            if df is None:
                raise ValueError("PNG export requires `df`")
            import plotly.express as px

            fig = px.bar(df)  # very basic; ChartView can pass a richer figure
            fig.write_image(str(path), format="png", width=900, height=500)
        else:
            raise ValueError(f"Unsupported export format: {file_format}")
    except Exception as e:
        log.error(f"Export failed: {e}")
        raise

    return {
        "path": str(path),
        "filename": filename,
        "size_bytes": path.stat().st_size,
        "format": file_format,
    }
