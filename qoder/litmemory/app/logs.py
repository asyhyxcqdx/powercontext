"""Append-only JSONL audit logs for retrieval and memory operations."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import config

_LOCK = threading.Lock()
RETRIEVAL_LOG = config.LOG_DIR / "retrieval_logs.jsonl"
MEMORY_LOG = config.LOG_DIR / "memory_logs.jsonl"


def _append(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    payload = {"ts": datetime.now().astimezone().isoformat(timespec="seconds"), **payload}
    line = json.dumps(payload, ensure_ascii=False)
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    return payload


def append_retrieval(payload: dict[str, Any]) -> dict[str, Any]:
    return _append(RETRIEVAL_LOG, payload)


def append_memory(payload: dict[str, Any]) -> dict[str, Any]:
    return _append(MEMORY_LOG, payload)


def _tail(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with _LOCK:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    items: list[dict[str, Any]] = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(items))


def recent_retrievals(limit: int = 20) -> list[dict[str, Any]]:
    return _tail(RETRIEVAL_LOG, limit)


def recent_memories(limit: int = 20) -> list[dict[str, Any]]:
    return _tail(MEMORY_LOG, limit)
