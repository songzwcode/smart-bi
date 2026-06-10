"""Structured logging via loguru.

Console output is colorized; file output is JSON-friendly for parsing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from loguru import logger as _loguru

_CONFIGURED = False


def _expand(p: str) -> str:
    return str(Path(p).expanduser())


def configure(
    level: str = "INFO",
    file: Optional[str] = None,
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """Configure the global loguru logger. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    _loguru.remove()
    _loguru.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
    )

    if file:
        file_path = _expand(file)
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        _loguru.add(
            file_path,
            level=level,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
            enqueue=True,
        )

    _CONFIGURED = True


def get_logger(name: str = "smart-bi"):
    """Return a bound logger with module context."""
    if not _CONFIGURED:
        configure()
    return _loguru.bind(module=name)


__all__ = ["configure", "get_logger"]
