"""Mock-only request-shape tests; NOT production API usage evidence."""

import io
import json
from unittest import mock

from sddflow.powercontext_client import PowerContext
from sddflow.minimax_client import generate


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_powercontext_memory_uses_http_endpoint_not_local_state(monkeypatch):
    captured = []

    def fake_urlopen(req, timeout):
        captured.append((req.full_url, json.loads(req.data)))
        if req.full_url.endswith("/v1/memory/remember"):
            return FakeResponse(json.dumps({"records": [{"artifact": "record-1"}]}).encode())
        if req.full_url.endswith("/v1/atomic-memory/list"):
            return FakeResponse(json.dumps({"items": [{"content": {"text": (
                "SDD_TASK_STATE task=inventory-min-stock-2026 | stage=validated | "
                "next=submit | sha256=abc | utc=2026-10-28T02:00:00Z")}}]}).encode())
        if req.full_url.endswith("/v1/atomic-memory/search"):
            return FakeResponse(b'{"hits": []}')
        raise AssertionError(req.full_url)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("sddflow.powercontext_client.save_json", lambda *args: None)
    monkeypatch.setattr(PowerContext, "scope", lambda self: "scope-from-server")
    pc = PowerContext()
    pc.write_state("validated", "submit", "abc")
    result = pc.read_state()
    assert "stage=validated" in result["latest"]
    assert captured[0][0].endswith("/v1/memory/remember")
    assert captured[1][0].endswith("/v1/atomic-memory/list")
    assert captured[1][1]["kind"] == "decision"
    assert captured[2][0].endswith("/v1/atomic-memory/search")
    assert all(obj["scope_id"] == "scope-from-server" for _, obj in captured)


def test_minimax_http_payload_and_trace_redact_key(monkeypatch):
    captured = []

    def fake_urlopen(req, timeout):
        captured.append(req)
        return FakeResponse(json.dumps({"id": "test-1", "model": "MiniMax-M2.5",
           "choices": [{"message": {"content": "def f():\n    pass\n"}, "finish_reason": "stop"}],
           "usage": {"total_tokens": 24}}).encode())

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setenv("MINIMAX_API_KEY", "TEST_KEY_DO_NOT_SHIP")
    code, proof = generate({"source_provenance": [{"path": "workshop/inventory.py", "content": "x"}]})
    assert code.startswith("def f")
    assert "TEST_KEY_DO_NOT_SHIP" not in json.dumps(proof)
    payload = json.loads(captured[0].data)
    assert payload["model"] == "MiniMax-M2.5"
    assert "source_provenance" in payload["messages"][1]["content"]
