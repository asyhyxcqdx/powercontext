"""End-to-end verification for a running LitMemory instance.

Usage:
    python scripts/verify.py --base http://127.0.0.1:8765

The script is intentionally read/write but idempotent: it seeds the demo
corpus, runs a hybrid search, writes one verification memory, recalls it,
and renders a weekly report. Exit code is non-zero when a check fails.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import httpx


def check(condition: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    client = httpx.Client(base_url=base, timeout=60)

    health = client.get("/api/health").json()
    print(json.dumps({"seekdb": health.get("seekdb"), "powercontext": health.get("powercontext"),
                      "embedding": health.get("embedding")}, ensure_ascii=False, indent=2))
    check(bool(health.get("seekdb", {}).get("ok")), "seekdb reachable",
          str(health.get("seekdb", {}).get("error") or health.get("seekdb", {}).get("collection")))
    check(bool(health.get("powercontext", {}).get("ok")), "PowerContext reachable",
          str(health.get("powercontext", {}).get("error") or health.get("powercontext", {}).get("scope")))

    seeded = client.post("/api/demo/seed").json()
    check(seeded.get("notes", 0) >= 10, "demo corpus seeded", f"{seeded.get('notes')} notes")
    print(f"       demo memories added: {seeded.get('memories')}")

    query = "如何在有限上下文预算内复用研究记忆？"
    found = client.post("/api/search", json={"query": query, "top_k": 5}).json()
    check(len(found.get("hits", [])) > 0, "hybrid search returns hits",
          f"engine={found.get('engine')} elapsed={found.get('elapsed_ms')}ms")
    print(f"       query: {query}")
    for hit in found["hits"][:3]:
        print(f"       - {hit.get('score')} · {hit.get('title')}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    marker = f"验证记忆 {stamp}：本周优先完成混合检索消融实验。"
    written = client.post("/api/memories", json={
        "kind": "working_note", "text": marker, "reason": "scripts/verify.py"
    }).json()
    entry_id = (written.get("entry") or {}).get("citation", {}).get("entry_id")
    check(bool(entry_id), "memory written to PowerContext", str(entry_id))

    recalled = client.post("/api/memories/recall", json={"query": "本周优先完成什么实验？"}).json()
    texts = " ".join(hit.get("text", "") for hit in recalled.get("hits", []))
    prepared = (recalled.get("prepared") or {}).get("content") or ""
    check(marker in texts or marker in prepared, "recall returns the new memory",
          f"mode={recalled.get('mode')} bytes={(recalled.get('prepared') or {}).get('content_bytes')}")

    report = client.post("/api/reports", json={}).json()
    markdown = report.get("markdown", "")
    check("## 二、阅读与关键发现" in markdown and "证据索引" in markdown, "weekly report rendered",
          f"{len(markdown)} chars, {report.get('stats')}")

    print("\nAll checks passed.")
    print(f"Open the UI at {base} and the API docs at {base}/docs")


if __name__ == "__main__":
    sys.exit(main())
