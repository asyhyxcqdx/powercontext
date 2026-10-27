"""seekdb-backed knowledge store: hybrid retrieval over papers and notes."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime
from typing import Any

import pyseekdb
from pyseekdb import (
    FulltextIndexConfig,
    HNSWConfiguration,
    Schema,
    VectorIndexConfig,
)

import config
import logs
from embeddings import Embedder

_WRITE_LOCK = threading.Lock()
_TERM_RE = re.compile(r"[\s,，。；;:：!！?？、/\\|()（）\[\]【】<>《》\"'`~]+")


def _flat(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        return value[0]
    if isinstance(value, list):
        return value
    return [value]


def _snippet(text: str, query: str, width: int = 170) -> str:
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    terms = [t for t in _TERM_RE.split(query or "") if len(t) >= 2]
    best = -1
    for term in terms:
        idx = clean.lower().find(term.lower())
        if idx >= 0:
            best = idx
            break
    if best < 0:
        return clean[:width] + ("…" if len(clean) > width else "")
    start = max(0, best - width // 3)
    end = min(len(clean), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(clean) else ""
    return prefix + clean[start:end] + suffix


def _split_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [t.strip() for t in str(value or "").replace("，", ",").split(",") if t.strip()]


class SeekdbStore:
    def __init__(self, embedder: Embedder) -> None:
        self.embedder = embedder
        self.client = None
        self.collection = None
        self.last_error: str | None = None

    # ------------------------------------------------------------------ setup
    @staticmethod
    def _ensure_database() -> None:
        name = config.SEEKDB_DATABASE
        if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
            raise ValueError(f"invalid database name: {name!r}")
        try:
            import pymysql
        except ImportError:
            return
        conn = pymysql.connect(
            host=config.SEEKDB_HOST,
            port=int(config.SEEKDB_PORT),
            user=config.SEEKDB_USER,
            password=config.SEEKDB_PASSWORD,
            database="mysql",
            charset="utf8mb4",
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{name}` "
                    "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                )
            conn.commit()
        finally:
            conn.close()

    def connect(self) -> None:
        self._ensure_database()
        self.client = pyseekdb.Client(
            host=config.SEEKDB_HOST,
            port=config.SEEKDB_PORT,
            tenant=config.SEEKDB_TENANT,
            database=config.SEEKDB_DATABASE,
            user=config.SEEKDB_USER,
            password=config.SEEKDB_PASSWORD,
        )
        dim = self.embedder.dim
        schema = Schema(
            vector_index=VectorIndexConfig(
                hnsw=HNSWConfiguration(dimension=dim, distance="cosine"),
                embedding_function=None,
            ),
            fulltext_index=FulltextIndexConfig(analyzer="ik"),
        )
        if self.client.has_collection(config.SEEKDB_COLLECTION):
            self.collection = self.client.get_collection(config.SEEKDB_COLLECTION)
            if self.collection.dimension and self.collection.dimension != dim:
                raise RuntimeError(
                    f"collection dimension {self.collection.dimension} != embedding dimension {dim}; "
                    "drop the collection or switch LITMEMORY_EMBEDDING_MODEL"
                )
        else:
            self.collection = self.client.create_collection(
                config.SEEKDB_COLLECTION, schema=schema
            )
        self.last_error = None

    def ensure(self) -> bool:
        if self.collection is not None:
            return True
        try:
            self.connect()
            return True
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False

    # ---------------------------------------------------------------- writes
    @staticmethod
    def _document(item: dict[str, Any]) -> str:
        title = str(item.get("title") or "").strip()
        body = str(item.get("content") or "").strip()
        tags = " ".join(_split_tags(item.get("tags")))
        return f"{title}\n{tags}\n{body}".strip()

    @staticmethod
    def _metadata(item: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().isoformat(timespec="seconds")
        year = item.get("year")
        try:
            year = int(year) if year not in (None, "", 0, "0") else 0
        except (TypeError, ValueError):
            year = 0
        return {
            "title": str(item.get("title") or "").strip()[:500],
            "kind": str(item.get("kind") or "note"),
            "authors": str(item.get("authors") or "")[:500],
            "year": year,
            "tags": ",".join(_split_tags(item.get("tags")))[:500],
            "source": str(item.get("source") or "")[:500],
            "created_at": str(item.get("created_at") or now),
            "updated_at": str(item.get("updated_at") or now),
        }

    def upsert(self, items: list[dict[str, Any]], refresh: bool = True) -> int:
        if not items:
            return 0
        if not self.ensure():
            raise RuntimeError(self.last_error or "seekdb is unavailable")
        ids = [str(item["id"]) for item in items]
        documents = [self._document(item) for item in items]
        metadatas = [self._metadata(item) for item in items]
        vectors = self.embedder.embed(documents)
        with _WRITE_LOCK:
            self.collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=vectors)
            if refresh:
                try:
                    self.collection.refresh_index()
                except Exception:  # noqa: BLE001 - index refresh is best-effort
                    pass
        return len(items)

    def delete(self, note_id: str) -> None:
        if not self.ensure():
            raise RuntimeError(self.last_error or "seekdb is unavailable")
        with _WRITE_LOCK:
            self.collection.delete(ids=[note_id])

    # ---------------------------------------------------------------- reads
    def _rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        ids = _flat(payload.get("ids"))
        documents = _flat(payload.get("documents"))
        metadatas = _flat(payload.get("metadatas"))
        distances = _flat(payload.get("distances"))
        rows: list[dict[str, Any]] = []
        for idx, note_id in enumerate(ids):
            meta = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
            document = documents[idx] if idx < len(documents) else ""
            parts = (document or "").split("\n", 2)
            rows.append(
                {
                    "id": note_id,
                    "document": document,
                    "content": parts[2] if len(parts) == 3 else document,
                    "distance": float(distances[idx]) if idx < len(distances) and distances[idx] is not None else None,
                    **meta,
                    "tags": _split_tags(meta.get("tags")),
                }
            )
        return rows

    def list_notes(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.ensure():
            raise RuntimeError(self.last_error or "seekdb is unavailable")
        payload = self.collection.get(limit=limit, include=["documents", "metadatas"])
        rows = self._rows(payload)
        rows.sort(key=lambda r: str(r.get("updated_at") or ""), reverse=True)
        for row in rows:
            row["snippet"] = _snippet(row.get("content", ""), "")
        return rows

    def count(self) -> int:
        if not self.ensure():
            return 0
        try:
            return int(self.collection.count())
        except Exception:  # noqa: BLE001
            return 0

    def get_one(self, note_id: str) -> dict[str, Any] | None:
        if not self.ensure():
            raise RuntimeError(self.last_error or "seekdb is unavailable")
        payload = self.collection.get(ids=[note_id], include=["documents", "metadatas"])
        rows = self._rows(payload)
        if not rows:
            return None
        row = rows[0]
        row["snippet"] = _snippet(row.get("content", ""), "")
        return row

    def _where(self, kinds: list[str] | None, year_from: int | None, year_to: int | None) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        if kinds:
            clauses.append({"kind": {"$in": kinds}})
        if year_from:
            clauses.append({"year": {"$gte": int(year_from)}})
        if year_to:
            clauses.append({"year": {"$lte": int(year_to)}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def search(
        self,
        query: str,
        *,
        kinds: list[str] | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        tags: list[str] | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is empty")
        if not self.ensure():
            raise RuntimeError(self.last_error or "seekdb is unavailable")

        started = time.perf_counter()
        where = self._where(kinds, year_from, year_to)
        wanted_tags = [t.lower() for t in (tags or [])]
        window = max(top_k * 3, 20)
        engine = "seekdb-hybrid"
        rows: list[dict[str, Any]] = []

        try:
            vector = self.embedder.embed([query])[0]
            payload = self.collection.hybrid_search(
                query={
                    "where_document": {"$contains": query},
                    "where": where,
                    "n_results": window,
                },
                knn={
                    "query_embeddings": [vector],
                    "where": where,
                    "n_results": window,
                },
                rank={"rrf": {"rank_window_size": 60, "rank_constant": 60}},
                n_results=window,
                include=["documents", "metadatas", "distances"],
            )
            rows = self._rows(payload)
        except Exception as exc:  # noqa: BLE001 - fall back to pure vector search
            self.last_error = f"hybrid: {type(exc).__name__}: {exc}"
            engine = "seekdb-vector"
            try:
                vector = self.embedder.embed([query])[0]
                payload = self.collection.query(
                    query_embeddings=[vector],
                    n_results=window,
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
                rows = self._rows(payload)
            except Exception as exc2:  # noqa: BLE001 - last-resort local scan
                self.last_error = f"vector: {type(exc2).__name__}: {exc2}"
                engine = "local-scan"
                rows = self.list_notes(limit=500)

        for row in rows:
            if wanted_tags:
                row_tags = {t.lower() for t in row.get("tags", [])}
                if not row_tags.intersection(wanted_tags):
                    continue
            row["snippet"] = _snippet(row.get("content", ""), query)
            distance = row.get("distance")
            if distance is None:
                row["score"] = None
            elif engine == "seekdb-hybrid":
                # RRF fusion returns a relevance score (higher is better) in `distances`.
                row["score"] = round(float(distance), 4)
            elif engine == "seekdb-vector":
                row["score"] = round(max(0.0, 1.0 - float(distance)), 4)
            else:
                row["score"] = None

        if engine == "seekdb-hybrid":
            rows.sort(key=lambda r: r.get("score") or 0.0, reverse=True)

        rows = rows[:top_k]
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        log_entry = logs.append_retrieval(
            {
                "op": "search",
                "query": query,
                "engine": engine,
                "filters": {
                    "kinds": kinds or [],
                    "year_from": year_from,
                    "year_to": year_to,
                    "tags": tags or [],
                },
                "top_k": top_k,
                "elapsed_ms": elapsed_ms,
                "hits": [
                    {
                        "id": r.get("id"),
                        "title": r.get("title"),
                        "kind": r.get("kind"),
                        "score": r.get("score"),
                        "distance": r.get("distance"),
                    }
                    for r in rows
                ],
                "collection": config.SEEKDB_COLLECTION,
                "database": config.SEEKDB_DATABASE,
            }
        )
        return {
            "hits": rows,
            "engine": engine,
            "elapsed_ms": elapsed_ms,
            "log": log_entry,
            "collection": config.SEEKDB_COLLECTION,
            "database": config.SEEKDB_DATABASE,
            "embedding": self.embedder.status(),
        }

    def status(self) -> dict[str, Any]:
        ok = self.ensure()
        return {
            "ok": ok,
            "error": self.last_error,
            "database": config.SEEKDB_DATABASE,
            "collection": config.SEEKDB_COLLECTION,
            "count": self.count() if ok else 0,
            "dimension": getattr(self.collection, "dimension", None) if ok else None,
        }
