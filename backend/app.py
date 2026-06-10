"""Desktop app entry point.

Starts the FastAPI backend in a background thread, waits for it to be ready,
then opens a native window via PyWebView loading the backend URL.

Usage:
    python -m backend.app
    smart-bi    (after `pip install -e .`)
"""
from __future__ import annotations

import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.server import start_server
from backend.utils import get_logger

log = get_logger(__name__)

# pywebview is imported lazily so the API server can run headless on a CI box
# or for `python -m backend.server` (if we add that later).


def _open_in_browser_fallback(url: str) -> None:
    """If pywebview isn't usable, fall back to opening the system browser."""
    log.warning("pywebview unavailable; opening URL in system browser instead.")
    webbrowser.open(url)


def main() -> int:
    settings = get_settings()

    # 1. Start backend
    try:
        server_thread, port = start_server(host=settings.app.host)
    except Exception as e:
        log.error(f"Failed to start backend: {e}")
        print(f"[ERROR] Could not start backend: {e}", file=sys.stderr)
        return 1

    url = f"http://{settings.app.host}:{port}/"
    print(f"[Smart BI] Backend running at {url}")
    print(f"[Smart BI] Open this URL if the window doesn't appear.")

    # 2. Try to launch a native window
    try:
        import webview   # type: ignore
    except Exception as e:
        log.warning(f"pywebview not available: {e}")
        _open_in_browser_fallback(url)
        # Keep server alive while browser is open
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    # 3. Pick window dimensions
    try:
        win_w, win_h = 1280, 800
    except Exception:
        win_w, win_h = 1280, 800

    window = webview.create_window(
        title=f"{settings.app.name} {settings.app.version}",
        url=url,
        width=win_w,
        height=win_h,
        min_size=(960, 640),
        resizable=True,
        text_select=True,
        confirm_close=False,
    )

    # 4. Optional: devtools when DEBUG
    debug = bool(settings.app.debug)

    try:
        webview.start(debug=debug)
    except Exception as e:
        log.error(f"webview.start failed: {e}")
        _open_in_browser_fallback(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
