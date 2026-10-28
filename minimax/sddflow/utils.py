from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_task() -> dict:
    return json.loads((ROOT / "task.json").read_text(encoding="utf-8"))


def safe_source(rel: str) -> Path:
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"Path escapes minimax root: {rel}")
    if not path.is_file():
        raise FileNotFoundError(f"Required source does not exist: {rel}")
    return path


def save_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def run_dir(prefix: str) -> Path:
    tag = timestamp().replace(":", "").replace(".", "").replace("-", "")
    folder = ROOT / "evidence" / "runs" / f"{tag}_{os.getpid()}_{prefix}"
    folder.mkdir(parents=True, exist_ok=False)
    return folder
