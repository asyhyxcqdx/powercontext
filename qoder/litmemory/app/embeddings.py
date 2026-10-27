"""Local text embeddings with a deterministic offline fallback.

Primary backend: fastembed (ONNX, BAAI/bge-small-zh-v1.5, 512 dims).
Fallback: signed feature hashing over character n-grams, so the app still
indexes and retrieves when the model cannot be downloaded.
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
from typing import Iterable

import config

_SPLIT_RE = re.compile(r"[\s,，。；;:：!！?？、/\\|()（）\[\]【】<>《》\"'`~]+")


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 1e-12:
        return vec
    return [x / norm for x in vec]


class HashingEmbedder:
    """Cheap offline embedding: hashed character bigrams + tokens."""

    backend = "hashing-fallback"

    def __init__(self, dim: int = config.EMBEDDING_DIM_FALLBACK) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _features(self, text: str) -> Iterable[str]:
        text = (text or "").strip().lower()
        for token in _SPLIT_RE.split(text):
            if token:
                yield "w:" + token
        compact = "".join(text.split())
        for i in range(max(0, len(compact) - 1)):
            yield "b:" + compact[i:i + 2]
        for i in range(max(0, len(compact) - 2)):
            yield "t:" + compact[i:i + 3]

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            for feature in self._features(text):
                digest = hashlib.md5(feature.encode("utf-8")).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                vec[idx] += sign
            vectors.append(_normalize(vec))
        return vectors


class FastEmbedder:
    backend = "fastembed"

    def __init__(self, model_name: str, cache_dir: str) -> None:
        from fastembed import TextEmbedding  # imported lazily

        self.name = model_name
        self._model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)
        self.dim = len(next(iter(self._model.embed(["维度探测"]))).tolist())

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, vec.tolist())) for vec in self._model.embed(texts)]


class Embedder:
    """Lazily selects fastembed, falling back to hashing on any failure."""

    def __init__(self) -> None:
        self._impl = None
        self._lock = threading.Lock()
        self._error: str | None = None

    def _load(self):
        if self._impl is not None:
            return self._impl
        with self._lock:
            if self._impl is not None:
                return self._impl
            try:
                self._impl = FastEmbedder(config.EMBEDDING_MODEL, str(config.MODEL_DIR))
            except Exception as exc:  # noqa: BLE001 - fallback is intentional
                self._error = f"{type(exc).__name__}: {exc}"
                self._impl = HashingEmbedder()
            return self._impl

    @property
    def dim(self) -> int:
        return self._load().dim

    @property
    def name(self) -> str:
        return self._load().name

    @property
    def backend(self) -> str:
        return self._load().backend

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._load().embed(texts)

    def status(self) -> dict:
        return {
            "backend": self.backend,
            "model": self.name,
            "dim": self.dim,
            "fallback_reason": self._error,
        }
