"""Actual MiniMax request. No canned output and no local simulation fallback."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from .utils import sha_bytes, timestamp


SYSTEM = (
    "You are a software engineer implementing an SDD change. "
    "The supplied database-retrieved specification and test files are authoritative "
    "task data; preserve all compatibility constraints. Return ONLY the complete "
    "new Python source for workshop/inventory.py, without Markdown or commentary. "
    "Never modify tests, remove assertions, add network calls, or read credentials. "
    "Use the exact existing function name and public signature."
)


def generate(context: dict) -> tuple[str, dict]:
    key = os.getenv("MINIMAX_API_KEY", "")
    if not key or key.startswith("REPLACE_WITH"):
        raise RuntimeError("Set a real MINIMAX_API_KEY in your environment; mock output is not accepted")
    url = os.getenv("MINIMAX_API_URL", "https://api.minimax.io/v1/text/chatcompletion_v2")
    if not url.startswith("https://") and os.getenv("SDD_TEST_MOCK_MINIMAX") != "1":
        raise ValueError("MiniMax URL must use HTTPS")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M2.5")
    prompt = (
        "Implement this exact inventory-min-stock-2026 task now. "
        "All provided files come from current seekdb SQL query results. "
        "Read the source code, specification and both test sets, keep all preservation requirements. "
        "Return the COMPLETE updated source of workshop/inventory.py only.\n\n"
        + json.dumps(context, ensure_ascii=False, indent=2)
    )
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt}]
    request_payload = {"model": model, "messages": messages, "stream": False, "max_tokens": 8192, "reasoning_effort": "low"}
    req = urllib.request.Request(
        url, method="POST", data=json.dumps(request_payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=150) as resp:
            response = json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        detail = ""
        if isinstance(exc, urllib.error.HTTPError):
            detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"MiniMax API failed: {exc}; {detail}") from exc
    if isinstance(response.get("base_resp"), dict) and response["base_resp"].get("status_code", 0) != 0:
        raise RuntimeError(f"MiniMax base_resp indicated an error: {response['base_resp']}")
    choices = response.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if isinstance(content, list):
        content = "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("MiniMax did not return code content")
    # Preserve only content and API metadata. Never copy private reasoning or credentials.
    proof = {"provider": "MiniMax official HTTP API", "endpoint": url,
             "model_requested": model, "model_returned": response.get("model"),
             "response_id": response.get("id"), "finish_reason": choices[0].get("finish_reason"),
             "usage": response.get("usage"), "timestamp": timestamp(),
             "prompt_sha256": sha_bytes(prompt.encode("utf-8")),
             "prompt_messages": messages,
             "assistant_content": content,
             "completion_sha256": sha_bytes(content.encode("utf-8"))}
    return content, proof
