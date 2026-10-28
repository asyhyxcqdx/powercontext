"""Official PowerContext HTTP API integration (no local-state substitute)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from .utils import ROOT, read_task, save_json, timestamp


class PowerContext:
    def __init__(self):
        self.base = os.getenv("POWERCONTEXT_URL", "http://127.0.0.1:8000").rstrip("/")
        self.token = os.getenv("POWERCONTEXT_TOKEN", "")

    def _request(self, path: str, payload: dict | None = None) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"{self.base}{path}", headers=headers,
            data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            detail = ""
            if isinstance(exc, urllib.error.HTTPError):
                detail = exc.read(2000).decode("utf-8", errors="replace")
            raise RuntimeError(f"PowerContext {path} unavailable: {exc}; {detail}") from exc

    def health(self) -> dict:
        return self._request("/health/live")

    def init_scope(self) -> str:
        task = read_task()
        response = self._request("/v1/scopes", {
            "title": "MiniMax SDD inventory competition demo",
            "summary": "Persist inventory-min-stock task progress across processes",
            "idempotency_key": "minimax-sdd-inventory-min-stock-2026",
        })
        scope = response.get("scope_id")
        if not scope:
            raise RuntimeError(f"Missing scope_id in PowerContext create_scope: {response}")
        save_json(ROOT / "runtime" / "powercontext_scope.json", {
            "scope_id": scope, "task_id": task["task_id"], "server": self.base})
        return scope

    def scope(self) -> str:
        path = ROOT / "runtime" / "powercontext_scope.json"
        if not path.is_file():
            raise RuntimeError("PowerContext scope has not been initialized; run init-scope")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("server") != self.base:
            raise RuntimeError("Scope belongs to a different server URL; run init-scope")
        return data["scope_id"]

    def write_state(self, stage: str, next_action: str, code_sha: str) -> dict:
        if any("\n" in x or "|" in x for x in [stage, next_action, code_sha]):
            raise ValueError("State fields must be single-line and cannot contain pipes")
        task = read_task()
        text = (f"SDD_TASK_STATE task={task['task_id']} | stage={stage} | "
                f"next={next_action} | sha256={code_sha} | utc={timestamp()}")
        result = self._request("/v1/memory/remember", {
            "scope_id": self.scope(), "kind": "decision", "text": text,
            "reason": "Verified task lifecycle event from the SDD demo runner",
        })
        if not result.get("records"):
            raise RuntimeError(f"PowerContext did not confirm a durable memory write: {result}")
        record = {"time": timestamp(), "scope_id": self.scope(), "request_text": text,
                  "confirmed_records": result["records"]}
        save_json(ROOT / "evidence" / "state_last_write.json", record)
        return record

    def read_state(self) -> dict:
        task = read_task()
        # Use list so evidence cannot disappear just because a full-text query tokenizes oddly.
        # PowerContext 1.4+ uses independent Atomic Memory artifacts. This is
        # an actual online list request, not a cached local JSON proof.
        listed = self._request("/v1/atomic-memory/list", {
            "scope_id": self.scope(), "kind": "decision", "limit": 100})
        try:
            searched = self._request("/v1/atomic-memory/search", {
                "scope_id": self.scope(), "query": "SDD_TASK_STATE", "mode": "text", "limit": 20})
        except RuntimeError as exc:
            # Listing is the authoritative read. Record search failures, do not hide them.
            searched = {"search_error": str(exc)}
        state_strings = sorted(set(_strings(listed, f"SDD_TASK_STATE task={task['task_id']}")))
        record = {"scope_id": self.scope(), "time": timestamp(), "records": state_strings,
                  "latest": max(state_strings, key=lambda s: s.rsplit("utc=", 1)[-1]) if state_strings else None,
                  "list_response": listed, "search_response": searched}
        save_json(ROOT / "evidence" / "state_last_read.json", record)
        return record

    def prepare(self, query: str) -> dict:
        return self._request("/v1/context/prepare", {
            "scope_id": self.scope(), "query": query, "max_bytes": 5000,
        })


def _strings(obj, contains: str) -> list[str]:
    found = []
    if isinstance(obj, str) and contains in obj:
        found.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            found.extend(_strings(value, contains))
    elif isinstance(obj, list):
        for value in obj:
            found.extend(_strings(value, contains))
    return found
