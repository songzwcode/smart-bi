"""Prompt templates bundled as text files in this directory."""
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def load(name: str) -> str:
    """Load a prompt template by file name (no extension needed)."""
    p = _PROMPTS_DIR / f"{name}.txt"
    if not p.exists():
        raise FileNotFoundError(f"Prompt template not found: {p}")
    return p.read_text(encoding="utf-8")
