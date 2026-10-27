"""LitMemory HTTP API and static SPA host.

Run with:  uvicorn main:app --app-dir app --host 0.0.0.0 --port 8765
"""
from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import config
import logs
import report as report_mod
import seed as seed_mod
from embeddings import Embedder
from memory import KINDS, MemoryService
from store import SeekdbStore

STATIC_DIR = Path(__file__).resolve().parent / "static"
STARTED_AT = time.time()

NOTE_KINDS = {"paper": "论文", "note": "笔记", "log": "记录"}

embedder = Embedder()
store = SeekdbStore(embedder)
memory = MemoryService()


# --------------------------------------------------------------------- models
class NotePayload(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    kind: str = "note"
    content: str = ""
    tags: str | list[str] = ""
    authors: str = ""
    year: int | None = None
    source: str = ""


class SearchPayload(BaseModel):
    query: str = Field(min_length=1)
    kinds: list[str] | None = None
    year_from: int | None = None
    year_to: int | None = None
    tags: list[str] | None = None
    top_k: int = Field(default=8, ge=1, le=20)


class MemoryPayload(BaseModel):
    kind: str = "fact"
    text: str = Field(min_length=1, max_length=8000)
    reason: str | None = None


class RecallPayload(BaseModel):
    query: str = "当前研究目标、偏好与进展"
    max_bytes: int = 8000


class ReportPayload(BaseModel):
    week_start: str | None = None
    week_end: str | None = None


# ---------------------------------------------------------------------- utils
def _iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _store_guard() -> None:
    if not store.ensure():
        raise HTTPException(status_code=503, detail=f"seekdb 不可用：{store.last_error}")


def _all_notes() -> list[dict[str, Any]]:
    _store_guard()
    try:
        return store.list_notes(limit=1000)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"读取 seekdb 失败：{exc}") from exc


def _note_payload(body: NotePayload) -> dict[str, Any]:
    kind = body.kind if body.kind in NOTE_KINDS else "note"
    return {
        "title": body.title.strip(),
        "kind": kind,
        "content": body.content,
        "tags": body.tags,
        "authors": body.authors,
        "year": body.year or 0,
        "source": body.source,
    }


def _demo_seed() -> dict[str, Any]:
    _store_guard()
    items = seed_mod.seed_payload()
    written = store.upsert(items)
    return {"notes": written, "ids": [item["id"] for item in items]}


# ------------------------------------------------------------------- lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    await memory.start()
    seeded_notes = 0
    seeded_memories = 0
    errors: list[str] = []
    if config.AUTOSEED:
        try:
            if store.ensure() and store.count() == 0:
                seeded_notes = _demo_seed()["notes"]
        except Exception as exc:  # noqa: BLE001 - app must still boot degraded
            errors.append(f"seed notes: {exc}")
        try:
            health = await memory.health()
            if health.get("ok"):
                seeded_memories = await seed_mod.ensure_memories(memory)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"seed memories: {exc}")
    app.state.seeded = {"notes": seeded_notes, "memories": seeded_memories, "errors": errors}
    yield
    await memory.close()


app = FastAPI(title="LitMemory", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------- routes
@app.get("/api/health")
async def health() -> dict[str, Any]:
    seekdb = store.status()
    powercontext = await memory.health()
    return {
        "app": "ok",
        "version": app.version,
        "uptime_seconds": round(time.time() - STARTED_AT, 1),
        "seekdb": seekdb,
        "powercontext": powercontext,
        "embedding": embedder.status(),
        "scope": config.POWERCONTEXT_SCOPE,
        "seeded": getattr(app.state, "seeded", {}),
    }


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    warning = None
    try:
        notes = _all_notes()
    except HTTPException as exc:
        warning = str(exc.detail)
    return {
        "notes": notes,
        "kinds": NOTE_KINDS,
        "memory_kinds": KINDS,
        "scope": config.POWERCONTEXT_SCOPE,
        "stats": {"notes": len(notes), "seekdb_ok": warning is None, "warning": warning},
    }


@app.get("/api/notes")
def list_notes(kind: str | None = None, q: str | None = None) -> dict[str, Any]:
    notes = _all_notes()
    if kind:
        notes = [n for n in notes if n.get("kind") == kind]
    if q:
        needle = q.strip().lower()
        notes = [
            n
            for n in notes
            if needle in str(n.get("title", "")).lower()
            or needle in str(n.get("content", "")).lower()
            or needle in str(n.get("tags", "")).lower()
        ]
    return {"notes": notes, "count": len(notes)}


@app.get("/api/notes/{note_id}")
def get_note(note_id: str) -> dict[str, Any]:
    _store_guard()
    try:
        note = store.get_one(note_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"读取 seekdb 失败：{exc}") from exc
    if note is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"note": note}


@app.post("/api/notes", status_code=201)
def create_note(body: NotePayload) -> dict[str, Any]:
    _store_guard()
    note_id = f"note_{uuid.uuid4().hex[:12]}"
    stamp = _iso_now()
    item = {
        "id": note_id,
        **_note_payload(body),
        "created_at": stamp,
        "updated_at": stamp,
    }
    try:
        store.upsert([item])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"写入 seekdb 失败：{exc}") from exc
    return {"note": item}


@app.put("/api/notes/{note_id}")
def update_note(note_id: str, body: NotePayload) -> dict[str, Any]:
    _store_guard()
    try:
        existing = store.get_one(note_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"读取 seekdb 失败：{exc}") from exc
    if existing is None:
        raise HTTPException(status_code=404, detail="条目不存在")
    item = {
        "id": note_id,
        **_note_payload(body),
        "created_at": existing.get("created_at") or _iso_now(),
        "updated_at": _iso_now(),
    }
    try:
        store.upsert([item])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"写入 seekdb 失败：{exc}") from exc
    return {"note": item}


@app.delete("/api/notes/{note_id}")
def delete_note(note_id: str) -> dict[str, Any]:
    _store_guard()
    try:
        store.delete(note_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"删除 seekdb 条目失败：{exc}") from exc
    return {"deleted": note_id}


@app.post("/api/search")
def search(body: SearchPayload) -> dict[str, Any]:
    _store_guard()
    try:
        return store.search(
            body.query,
            kinds=body.kinds,
            year_from=body.year_from,
            year_to=body.year_to,
            tags=body.tags,
            top_k=body.top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"检索失败：{exc}") from exc


@app.get("/api/retrieval-logs")
def retrieval_logs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    return {"logs": logs.recent_retrievals(limit)}


@app.get("/api/memories")
async def list_memories() -> dict[str, Any]:
    try:
        payload = await memory.list_entries()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"PowerContext 不可用：{exc}") from exc
    return {**payload, "kinds": KINDS}


@app.post("/api/memories", status_code=201)
async def add_memory(body: MemoryPayload) -> dict[str, Any]:
    kind = body.kind if body.kind in KINDS else "fact"
    try:
        result = await memory.remember(kind, body.text, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"写入 PowerContext 失败：{exc}") from exc
    return {**result, "kind_label": KINDS.get(kind, kind)}


@app.post("/api/memories/recall")
async def recall(body: RecallPayload) -> dict[str, Any]:
    try:
        return await memory.recall(body.query, body.max_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"PowerContext 不可用：{exc}") from exc


@app.get("/api/memory-logs")
def memory_logs(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    return {"logs": logs.recent_memories(limit)}


@app.post("/api/reports")
async def create_report(body: ReportPayload) -> dict[str, Any]:
    notes = _all_notes()
    entries: list[dict[str, Any]] = []
    prepared_text = None
    memory_error = None
    try:
        memories = await memory.list_entries()
        entries = memories.get("entries", [])
        recalled = await memory.recall("本周研究进展、已定结论与下周计划", 6000)
        prepared = recalled.get("prepared") or {}
        prepared_text = prepared.get("content")
    except Exception as exc:  # noqa: BLE001 - report still works from seekdb alone
        memory_error = f"{type(exc).__name__}: {exc}"
    result = report_mod.build_report(
        notes,
        entries,
        prepared_text,
        week_start=body.week_start,
        week_end=body.week_end,
        scope=config.POWERCONTEXT_SCOPE,
    )
    result["memory_error"] = memory_error
    result["generated_at"] = _iso_now()
    return result


@app.post("/api/demo/seed")
async def demo_seed() -> dict[str, Any]:
    try:
        seeded = _demo_seed()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"写入示例数据失败：{exc}") from exc
    memories = 0
    memory_error = None
    try:
        memories = await seed_mod.ensure_memories(memory)
    except Exception as exc:  # noqa: BLE001
        memory_error = f"{type(exc).__name__}: {exc}"
    return {**seeded, "memories": memories, "memory_error": memory_error}


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    notes = _all_notes()
    by_kind: dict[str, int] = {}
    for note in notes:
        key = str(note.get("kind") or "note")
        by_kind[key] = by_kind.get(key, 0) + 1
    return {
        "notes": len(notes),
        "by_kind": by_kind,
        "seekdb": store.status(),
        "embedding": embedder.status(),
        "recent_retrievals": len(logs.recent_retrievals(100)),
        "recent_memory_ops": len(logs.recent_memories(100)),
        "scope": config.POWERCONTEXT_SCOPE,
    }


@app.get("/api/export")
async def export() -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    try:
        notes = _all_notes()
    except HTTPException:
        pass
    memories: list[dict[str, Any]] = []
    memory_error = None
    try:
        memories = (await memory.list_entries()).get("entries", [])
    except Exception as exc:  # noqa: BLE001
        memory_error = f"{type(exc).__name__}: {exc}"
    return {
        "generated_at": _iso_now(),
        "seekdb": {
            "database": config.SEEKDB_DATABASE,
            "collection": config.SEEKDB_COLLECTION,
            "notes": notes,
        },
        "powercontext": {
            "scope": config.POWERCONTEXT_SCOPE,
            "entries": memories,
            "error": memory_error,
        },
        "logs": {
            "retrieval": logs.recent_retrievals(200),
            "memory": logs.recent_memories(200),
        },
    }


# --------------------------------------------------------------------- static
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.svg")
def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=config.APP_HOST, port=config.APP_PORT)
