"""User-level settings persistence.

Stores runtime user choices (current LLM, current DB connection, etc.) in
`~/.smart-bi/user_settings.json`. Distinct from:

  * `config.yaml` — repo defaults (developer-side)
  * `.env`        — secrets / environment overrides

If the file is missing or malformed, defaults are used silently.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from backend.config import get_settings
from backend.utils import get_logger

log = get_logger(__name__)


def _settings_path() -> Path:
    s = get_settings()
    data_dir = s.abs_path(s.paths.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "user_settings.json"


_lock = threading.RLock()
_cache: Optional[dict[str, Any]] = None


def _read_from_disk() -> dict[str, Any]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            log.warning(f"user_settings.json is not a dict; ignoring")
            return {}
        return data
    except Exception as e:
        log.warning(f"Failed to read user_settings.json: {e}")
        return {}


def _write_to_disk(data: dict[str, Any]) -> None:
    path = _settings_path()
    tmp = path.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        log.warning(f"Failed to write user_settings.json: {e}")
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _load() -> dict[str, Any]:
    global _cache
    with _lock:
        if _cache is None:
            _cache = _read_from_disk()
        return _cache


def get_all() -> dict[str, Any]:
    """Return a deep-ish copy of the persisted user settings."""
    with _lock:
        return dict(_load())


def get(key: str, default: Any = None) -> Any:
    with _lock:
        return _load().get(key, default)


def set_value(key: str, value: Any) -> None:
    """Persist a single top-level key."""
    with _lock:
        data = dict(_load())
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
        _write_to_disk(data)
        global _cache
        _cache = data


def update(patch: dict[str, Any]) -> None:
    """Merge a dict into the persisted settings."""
    with _lock:
        data = dict(_load())
        for k, v in patch.items():
            if v is None:
                data.pop(k, None)
            else:
                data[k] = v
        _write_to_disk(data)
        global _cache
        _cache = data


def reset() -> None:
    """Delete the persisted settings file (and clear cache)."""
    global _cache
    with _lock:
        path = _settings_path()
        try:
            if path.exists():
                path.unlink()
        except Exception as e:
            log.warning(f"Failed to delete user_settings.json: {e}")
        _cache = {}


# ---- typed helpers --------------------------------------------------------


def get_llm() -> Optional[dict[str, Any]]:
    """Return saved LLM choice as a dict with keys:
    provider, model, ollama_url, custom_url, custom_api_key (or None)."""
    raw = get("llm")
    if not isinstance(raw, dict):
        return None
    return {
        "provider": raw.get("provider"),
        "model": raw.get("model"),
        "ollama_url": raw.get("ollama_url"),
        "custom_url": raw.get("custom_url"),
        "custom_api_key": raw.get("custom_api_key"),
    }


def set_llm(
    provider: str,
    model: Optional[str] = None,
    ollama_url: Optional[str] = None,
    custom_url: Optional[str] = None,
    custom_api_key: Optional[str] = None,
) -> None:
    set_value(
        "llm",
        {
            "provider": provider,
            "model": model,
            "ollama_url": ollama_url,
            "custom_url": custom_url,
            "custom_api_key": custom_api_key,
        },
    )


def get_db() -> Optional[dict[str, Any]]:
    """Return saved DB connection config (matches ConnectionConfig schema)."""
    raw = get("db")
    if not isinstance(raw, dict):
        return None
    return raw


def set_db(config: dict[str, Any]) -> None:
    set_value("db", config)


def get_ui_prefs() -> dict[str, Any]:
    """Return UI preferences (e.g. show_thinking)."""
    raw = get("ui")
    if not isinstance(raw, dict):
        return {}
    return raw


def set_ui_pref(key: str, value: Any) -> None:
    with _lock:
        data = dict(_load())
        ui = dict(data.get("ui") or {})
        if value is None:
            ui.pop(key, None)
        else:
            ui[key] = value
        if ui:
            data["ui"] = ui
        else:
            data.pop("ui", None)
        _write_to_disk(data)
        global _cache
        _cache = data
