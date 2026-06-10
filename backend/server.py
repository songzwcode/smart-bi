"""FastAPI app factory.

Binds to 127.0.0.1 on a free port in `app.port_range`. Mounts the built
frontend (`backend/static/`) as static files when available, so PyWebView
can load `http://127.0.0.1:{port}/` directly.
"""
from __future__ import annotations

import socket
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routes import router as api_router
from backend.config import get_settings
from backend.data.introspect import introspect_schema
from backend.data.schema_rag import get_schema_rag
from backend.utils import get_logger

log = get_logger(__name__)


def _find_free_port(host: str, start: int, end: int) -> int:
    for p in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"No free port found in {start}-{end}")


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Warm up schema in the background so we don't block startup
        # (chromadb's first-time use can be slow on cold caches).
        def _warmup():
            try:
                info = introspect_schema()
                try:
                    get_schema_rag().reindex(info)
                except Exception as e:
                    log.warning(f"Initial schema RAG index failed: {e}")
            except Exception as e:
                log.warning(f"Initial schema introspection failed: {e}")

        threading.Thread(target=_warmup, daemon=True, name="schema-warmup").start()
        log.info("Smart BI backend ready.")
        yield

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        lifespan=lifespan,
    )

    # Permissive CORS for dev (production is bound to 127.0.0.1 only)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/api/info")
    def info():
        s = get_settings()
        return {
            "name": s.app.name,
            "version": s.app.version,
            "host": s.app.host,
            "port": app.state.port,
        }

    # Static frontend (if built)
    static_dir = settings.abs_path(settings.paths.static_dir)
    if static_dir.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=str(static_dir / "assets")),
            name="assets",
        )

        @app.get("/")
        def root():
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))

        @app.get("/{full_path:path}")
        def spa(full_path: str):
            # If path matches a file in static_dir, serve it
            target = static_dir / full_path
            if target.is_file():
                return FileResponse(str(target))
            # otherwise fall back to index.html for SPA routing
            index = static_dir / "index.html"
            if index.exists():
                return FileResponse(str(index))
            return JSONResponse({"error": "frontend not built"}, status_code=404)
    else:
        @app.get("/")
        def root_no_static():
            return JSONResponse(
                {
                    "name": settings.app.name,
                    "version": settings.app.version,
                    "message": "frontend not built; run `cd frontend && npm run build`",
                }
            )

    return app


class ServerThread(threading.Thread):
    """Run uvicorn in a background thread (for the desktop app)."""

    def __init__(self, host: str, port: int):
        super().__init__(daemon=True, name="smart-bi-server")
        self.host = host
        self.port = port
        self._server: Optional[uvicorn.Server] = None
        self._started = threading.Event()

    def run(self) -> None:
        app = create_app()
        app.state.port = self.port
        config = uvicorn.Config(
            app=app,
            host=self.host,
            port=self.port,
            log_level="info",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        async def _on_started():
            self._started.set()

        self._server.config.callback_notify = _on_started  # type: ignore[attr-defined]
        self._server.run()

    def wait_ready(self, timeout: float = 60.0) -> None:
        """Block until the server has started (or timeout)."""
        # Polling fallback if callback isn't supported
        import time
        import urllib.request

        deadline = time.time() + timeout
        url = f"http://{self.host}:{self.port}/api/health"
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, timeout=0.5)
                return
            except Exception:
                time.sleep(0.05)
        raise RuntimeError("Server did not become ready in time")


def start_server(host: Optional[str] = None) -> tuple[ServerThread, int]:
    """Start the backend server in a daemon thread, return (thread, port)."""
    s = get_settings()
    host = host or s.app.host
    port = _find_free_port(host, s.app.port_range[0], s.app.port_range[1])
    t = ServerThread(host, port)
    t.start()
    t.wait_ready(timeout=60.0)
    log.info(f"Server started at http://{host}:{port}")
    return t, port


def main() -> int:
    """Run the server in the foreground (used by `python -m backend.server`)."""
    import uvicorn

    s = get_settings()
    host = s.app.host
    port = _find_free_port(host, s.app.port_range[0], s.app.port_range[1])
    app = create_app()
    app.state.port = port
    log.info(f"Smart BI server listening on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
