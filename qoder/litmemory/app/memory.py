"""PowerContext memory: durable, cross-session research context."""
from __future__ import annotations

import time
from typing import Any

from powercontext.client import PowerContextClient
from powercontext.http import (
    ListMemoryEntriesRequest,
    PrepareContextRequest,
    RememberMemoryRequest,
    SearchMemoryRequest,
)

import config
import logs

KINDS = {
    "preference": "研究偏好",
    "decision": "已定结论",
    "working_note": "进行中",
    "fact": "重要事实",
    "constraint": "约束条件",
}


def _dump(model: Any) -> Any:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json", by_alias=True)
    return model


class MemoryService:
    def __init__(self) -> None:
        self.client: PowerContextClient | None = None
        self.last_error: str | None = None

    async def start(self) -> None:
        self.client = PowerContextClient(
            config.POWERCONTEXT_URL, timeout=config.POWERCONTEXT_TIMEOUT
        )

    async def close(self) -> None:
        if self.client is not None:
            await self.client.aclose()

    def _client(self) -> PowerContextClient:
        if self.client is None:
            self.client = PowerContextClient(
                config.POWERCONTEXT_URL, timeout=config.POWERCONTEXT_TIMEOUT
            )
        return self.client

    async def health(self) -> dict[str, Any]:
        try:
            readiness = await self._client().get_readiness()
            data = _dump(readiness)
            self.last_error = None
            return {"ok": True, "scope": config.POWERCONTEXT_SCOPE, "readiness": data}
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.last_error = f"{type(exc).__name__}: {exc}"
            return {"ok": False, "scope": config.POWERCONTEXT_SCOPE, "error": self.last_error}

    async def remember(self, kind: str, text: str, reason: str | None = None) -> dict[str, Any]:
        kind = (kind or "fact").strip()
        text = " ".join((text or "").split())
        if not text:
            raise ValueError("memory text is empty")
        started = time.perf_counter()
        try:
            response = await self._client().remember_memory(
                RememberMemoryRequest(
                    scope_id=config.POWERCONTEXT_SCOPE,
                    kind=kind,
                    text=text[:8000],
                    reason=(reason or "")[:500] or None,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logs.append_memory(
                {
                    "op": "remember",
                    "ok": False,
                    "kind": kind,
                    "text": text[:500],
                    "error": f"{type(exc).__name__}: {exc}",
                    "scope": config.POWERCONTEXT_SCOPE,
                }
            )
            raise
        payload = _dump(response)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logs.append_memory(
            {
                "op": "remember",
                "ok": True,
                "kind": kind,
                "text": text[:500],
                "reason": reason or "",
                "elapsed_ms": elapsed_ms,
                "entry": payload.get("entry"),
                "scope": config.POWERCONTEXT_SCOPE,
            }
        )
        return {"entry": payload.get("entry"), "elapsed_ms": elapsed_ms, "kind": kind}

    async def search(self, query: str, limit: int = 10) -> dict[str, Any]:
        query = (query or "").strip()
        if not query:
            raise ValueError("query is empty")
        started = time.perf_counter()
        response = await self._client().search_memory(
            SearchMemoryRequest(scope_id=config.POWERCONTEXT_SCOPE, query=query, limit=limit)
        )
        payload = _dump(response)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logs.append_memory(
            {
                "op": "search",
                "ok": True,
                "query": query,
                "mode": payload.get("mode"),
                "elapsed_ms": elapsed_ms,
                "hits": [
                    {"text": h.get("text"), "score": h.get("score"), "matched_by": h.get("matched_by")}
                    for h in payload.get("hits", [])
                ],
                "scope": config.POWERCONTEXT_SCOPE,
            }
        )
        return {**payload, "elapsed_ms": elapsed_ms}

    async def recall(self, query: str, max_bytes: int = 8000) -> dict[str, Any]:
        query = (query or "").strip() or "当前研究目标、偏好与进展"
        started = time.perf_counter()
        hits: dict[str, Any] = {"hits": [], "mode": None}
        search_error = None
        try:
            hits = await self.search(query, limit=10)
        except Exception as exc:  # noqa: BLE001 - prepared context still useful
            search_error = f"{type(exc).__name__}: {exc}"
        prepared = await self._client().prepare_context(
            PrepareContextRequest(
                scope_id=config.POWERCONTEXT_SCOPE,
                query=query,
                max_bytes=max(512, min(32768, int(max_bytes))),
            )
        )
        payload = _dump(prepared)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logs.append_memory(
            {
                "op": "prepare",
                "ok": True,
                "query": query,
                "status": payload.get("status"),
                "content_bytes": payload.get("content_bytes"),
                "elapsed_ms": elapsed_ms,
                "scope": config.POWERCONTEXT_SCOPE,
                "search_error": search_error,
            }
        )
        return {
            "query": query,
            "hits": hits.get("hits", []),
            "mode": hits.get("mode"),
            "prepared": payload,
            "elapsed_ms": elapsed_ms,
            "search_error": search_error,
        }

    async def list_entries(self) -> dict[str, Any]:
        response = await self._client().list_memory_entries(
            ListMemoryEntriesRequest(scope_id=config.POWERCONTEXT_SCOPE, include_inactive=False)
        )
        payload = _dump(response)
        entries = []
        for entry in payload.get("entries", []):
            entries.append({**entry, "kind_label": KINDS.get(entry.get("kind"), entry.get("kind"))})
        entries.sort(key=lambda e: str(e.get("citation", {}).get("entry_id", "")), reverse=True)
        return {"entries": entries, "scope": config.POWERCONTEXT_SCOPE}
