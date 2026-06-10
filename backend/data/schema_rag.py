"""Schema RAG: build & search a vector index over table/column descriptions.

Uses ChromaDB with the default embedding function (no extra model download on
first run for tiny collections, but sentence-transformers is recommended for
real workloads).

ChromaDB is an optional dependency — when not installed, the system gracefully
degrades: reindex() and retrieve() become no-ops and context_for() returns "".
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.data.introspect import SchemaInfo, TableInfo, introspect_schema
from backend.utils import get_logger

log = get_logger(__name__)

# Optional chromadb import — system works without it
try:
    import chromadb  # type: ignore
    from chromadb.config import Settings as ChromaSettings  # type: ignore

    CHROMADB_AVAILABLE = True
except Exception as e:  # pragma: no cover - exercised on missing dep
    chromadb = None
    ChromaSettings = None
    CHROMADB_AVAILABLE = False
    log.warning(f"chromadb not available; SchemaRAG disabled ({type(e).__name__})")


def _doc_for_table(t: TableInfo) -> str:
    """Produce a textual document for a table, used for embedding + retrieval."""
    lines = [f"Table: {t.name}"]
    if t.comment:
        lines.append(f"Description: {t.comment}")
    if t.columns:
        col_str = ", ".join(
            f"{c['name']} ({c['type']}{'' if c.get('nullable', True) else ', NOT NULL'})"
            for c in t.columns
        )
        lines.append(f"Columns: {col_str}")
    if t.primary_key:
        lines.append(f"Primary key: {', '.join(t.primary_key)}")
    if t.foreign_keys:
        fk_str = "; ".join(
            f"{','.join(fk['columns'])} -> {fk['referred_table']}({','.join(fk['referred_columns'])})"
            for fk in t.foreign_keys
            if fk.get("referred_table")
        )
        if fk_str:
            lines.append(f"Foreign keys: {fk_str}")
    if t.sample:
        lines.append(f"Sample rows: {t.sample[:2]}")
    return "\n".join(lines)


class SchemaRAG:
    """ChromaDB-backed schema retrieval. No-op when chromadb is unavailable."""

    COLLECTION = "schema"

    def __init__(self, persist_dir: Optional[Path] = None):
        self._enabled = CHROMADB_AVAILABLE
        self._client = None
        self._coll = None
        self._lock = threading.RLock()
        self._version = 0

        # Respect the agent config flag — turn off the whole subsystem cleanly
        # without paying for a chroma PersistentClient (which would download
        # a 79MB embedding model on first use).
        try:
            if not get_settings().agent.enable_schema_rag:
                log.info("SchemaRAG disabled by config (agent.enable_schema_rag=false).")
                self._enabled = False
                return
        except Exception:
            pass

        if not self._enabled:
            log.info("SchemaRAG running in degraded mode (no chromadb).")
            return

        s = get_settings()
        persist_dir = persist_dir or s.abs_path(s.paths.data_dir) / "chroma"
        persist_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._client = chromadb.PersistentClient(  # type: ignore
                path=str(persist_dir),
                settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),  # type: ignore
            )
            self._coll = self._client.get_or_create_collection(
                name=self.COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as e:
            log.warning(f"Failed to init ChromaDB; disabling RAG: {e}")
            self._enabled = False
            self._client = None
            self._coll = None

    def _bump(self):
        with self._lock:
            self._version += 1

    @property
    def version(self) -> int:
        return self._version

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reindex(self, schema: Optional[SchemaInfo] = None) -> int:
        """Rebuild the index from the current database schema. Returns doc count."""
        if not self._enabled or self._coll is None:
            return 0
        schema = schema or introspect_schema()
        docs, ids, metas = [], [], []
        for t in schema.tables:
            docs.append(_doc_for_table(t))
            ids.append(f"table::{t.name}")
            metas.append(
                {
                    "table": t.name,
                    "row_count": t.row_count,
                    "dialect": schema.dialect,
                }
            )
        with self._lock:
            try:
                existing = self._coll.get()
                if existing and existing["ids"]:
                    self._coll.delete(ids=existing["ids"])
            except Exception:
                pass
            if docs:
                try:
                    self._coll.add(documents=docs, ids=ids, metadatas=metas)
                except Exception as e:
                    log.warning(f"SchemaRAG add failed: {e}")
            self._bump()
            log.info(f"SchemaRAG reindexed: {len(docs)} tables")
            return len(docs)

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        """Return top-k relevant schema documents."""
        if not self._enabled or self._coll is None:
            return []
        with self._lock:
            try:
                res = self._coll.query(query_texts=[query], n_results=top_k)
            except Exception as e:
                log.warning(f"SchemaRAG retrieve failed: {e}")
                return []
        out: list[dict] = []
        for i, doc in enumerate(res.get("documents", [[]])[0]):
            meta = (res.get("metadatas", [[]])[0] or [{}])[i] if res.get("metadatas") else {}
            dist = (res.get("distances", [[]])[0] or [None])[i] if res.get("distances") else None
            out.append({"document": doc, "metadata": meta, "distance": dist})
        return out

    def context_for(self, query: str, top_k: int = 5) -> str:
        """Return concatenated relevant docs as a single text block."""
        if not self._enabled:
            return ""
        hits = self.retrieve(query, top_k=top_k)
        if not hits:
            return ""
        parts = ["# Relevant schema (retrieved)"]
        for h in hits:
            parts.append(h["document"])
        return "\n\n".join(parts)


_singleton: Optional[SchemaRAG] = None
_lock = threading.Lock()


def get_schema_rag() -> SchemaRAG:
    global _singleton
    with _lock:
        if _singleton is None:
            _singleton = SchemaRAG()
        return _singleton
