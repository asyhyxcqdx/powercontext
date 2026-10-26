# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Self-contained UTF-8 context packs and verified prefix deltas."""

# ruff: noqa: TRY003

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

_PACK_SCHEMA = "powercontext.context-pack.v1"
_DELTA_SCHEMA = "powercontext.context-pack-delta.v1"


class ContextPackError(ValueError):
    """A context packet violates the wire or chunk contract."""


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContextPackError("duplicate JSON field")
        result[key] = value
    return result


def _read_payload(data: bytes, schema: str, fields: set[str]) -> dict[str, Any]:
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
    except (ValueError, AttributeError) as error:
        raise ContextPackError("invalid UTF-8 JSON packet") from error
    if not isinstance(payload, dict) or set(payload) != fields or payload["schema"] != schema:
        raise ContextPackError("invalid packet fields or schema")
    return payload


def _validate_items(items: tuple[bytes, ...]) -> None:
    if not isinstance(items, tuple) or any(not isinstance(item, bytes) for item in items):
        raise ContextPackError("chunks must be a tuple of bytes")
    try:
        for item in items:
            item.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ContextPackError("each chunk must be valid UTF-8") from error


def _encode_items(items: tuple[bytes, ...]) -> list[str]:
    return [base64.b64encode(item).decode("ascii") for item in items]


def _decode_items(values: object) -> tuple[bytes, ...]:
    if not isinstance(values, list):
        raise ContextPackError("chunks must be a Base64 string array")
    encoded: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ContextPackError("chunks must be a Base64 string array")
        encoded.append(value)
    try:
        items = tuple(base64.b64decode(value, validate=True) for value in encoded)
    except (ValueError, binascii.Error) as error:
        raise ContextPackError("invalid Base64 chunk") from error
    if _encode_items(items) != values:
        raise ContextPackError("chunks must use canonical standard Base64")
    _validate_items(items)
    return items


def _validate_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
        raise ContextPackError("invalid digest format")


@dataclass(frozen=True, slots=True)
class ContextPack:
    """An immutable complete packet with its canonical serialized bytes."""

    items: tuple[bytes, ...]
    digest: str = field(init=False)
    _wire: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        _validate_items(self.items)
        payload: dict[str, Any] = {"schema": _PACK_SCHEMA, "items": _encode_items(self.items)}
        digest = "sha256:" + hashlib.sha256(_json_bytes(payload)).hexdigest()
        payload.update(digest=digest, byte_count=0)
        wire = _json_bytes(payload)
        while payload["byte_count"] != len(wire):
            payload["byte_count"] = len(wire)
            wire = _json_bytes(payload)
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "_wire", wire)

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        return cls(items)

    @classmethod
    def from_content(cls, content: str, *, chunk_bytes: int = 512) -> ContextPack:
        if type(chunk_bytes) is not int or chunk_bytes <= 0:
            raise ContextPackError("chunk_bytes must be a positive integer")
        try:
            raw = content.encode("utf-8")
        except (UnicodeError, AttributeError) as error:
            raise ContextPackError("content must be valid UTF-8 text") from error
        chunks = []
        start = 0
        while start < len(raw):
            end = min(start + chunk_bytes, len(raw))
            while end < len(raw) and end > start and raw[end] & 0xC0 == 0x80:
                end -= 1
            if end == start:
                raise ContextPackError("chunk_bytes cannot hold a complete UTF-8 character")
            chunks.append(raw[start:end])
            start = end
        return cls.build(tuple(chunks))

    @property
    def byte_count(self) -> int:
        return len(self._wire)

    def to_bytes(self) -> bytes:
        return self._wire

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPack:
        payload = _read_payload(data, _PACK_SCHEMA, {"schema", "items", "digest", "byte_count"})
        pack = cls.build(_decode_items(payload["items"]))
        if payload["digest"] != pack.digest:
            raise ContextPackError("pack digest mismatch")
        if type(payload["byte_count"]) is not int or payload["byte_count"] != pack.byte_count:
            raise ContextPackError("pack byte count mismatch")
        return pack


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """A target suffix with independently checked base and target identities."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    def __post_init__(self) -> None:
        _validate_digest(self.base_digest)
        _validate_digest(self.target_digest)
        if type(self.prefix_items) is not int or self.prefix_items < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")
        _validate_items(self.appended)

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        prefix = 0
        for before, after in zip(base.items, target.items, strict=False):
            if before != after:
                break
            prefix += 1
        return cls(base.digest, target.digest, prefix, target.items[prefix:])

    def to_bytes(self) -> bytes:
        return _json_bytes({
            "schema": _DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": _encode_items(self.appended),
        })

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def from_bytes(cls, data: bytes) -> ContextPackDelta:
        payload = _read_payload(
            data, _DELTA_SCHEMA, {"schema", "base_digest", "target_digest", "prefix_items", "appended"}
        )
        return cls(
            payload["base_digest"],
            payload["target_digest"],
            payload["prefix_items"],
            _decode_items(payload["appended"]),
        )


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    if base.digest != delta.base_digest:
        raise ContextPackError("delta base digest mismatch")
    if delta.prefix_items > len(base.items):
        raise ContextPackError("delta prefix exceeds the base")
    target = ContextPack.build(base.items[: delta.prefix_items] + delta.appended)
    if target.digest != delta.target_digest:
        raise ContextPackError("delta target digest mismatch")
    return target


__all__ = ["ContextPack", "ContextPackDelta", "ContextPackError", "apply_context_pack_delta"]
