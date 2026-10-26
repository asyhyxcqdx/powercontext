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

"""Independent wire corruption and UTF-8 chunk boundary checks."""

import asyncio
import json
from typing import Any

import pytest

from powercontext.builtin.runtime import BuiltinConfig, PrepareContextRequest, open_builtin_runtime
from powercontext.builtin.runtime.context_pack import (
    ContextPack,
    ContextPackDelta,
    ContextPackError,
    apply_context_pack_delta,
)
from powercontext.builtin.scope import ScopeDraft


@pytest.mark.parametrize("size", [4, 5, 7, 512])
def test_mixed_unicode_chunks_are_bounded_and_deterministic(size: int) -> None:
    content = "a海🌊\r\nbé" * 100
    pack = ContextPack.from_content(content, chunk_bytes=size)
    assert pack == ContextPack.from_content(content, chunk_bytes=size)
    assert b"".join(pack.items) == content.encode()
    assert all(0 < len(item) <= size and isinstance(item.decode(), str) for item in pack.items)
    assert ContextPack.from_bytes(pack.to_bytes()) == pack


@pytest.mark.parametrize(
    "patch",
    [
        {"byte_count": True},
        {"byte_count": 999},
        {"extra": 0},
        {"items": ["!not base64!"]},
        {"items": ["/w=="]},
        {"items": [5]},
        {"items": "YWJj"},
    ],
)
def test_pack_rejects_invalid_wire_fields(patch: dict[str, Any]) -> None:
    payload = json.loads(ContextPack.build((b"abc",)).to_bytes())
    payload.update(patch)
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(json.dumps(payload).encode())


def test_duplicate_json_keys_are_rejected() -> None:
    wire = ContextPack.build((b"abc",)).to_bytes()
    with pytest.raises(ContextPackError):
        ContextPack.from_bytes(b'{"byte_count":0,' + wire[1:])


def test_runtime_empty_context_replaces_a_nonempty_pack() -> None:
    async def run() -> None:
        base = ContextPack.from_content("previous context")
        async with open_builtin_runtime(BuiltinConfig()) as runtime:
            assert runtime.scopes is not None
            scope = await runtime.scopes.create(
                ScopeDraft(title="Empty context", summary="No sources", idempotency_key="empty-context-test")
            )
            context = runtime.context.for_scope(scope.scope_id)
            request = PrepareContextRequest(query="absent", max_bytes=4096)
            first = await context.prepare_incremental(request)
            delta = await context.prepare_incremental(request, base_pack=base)
        assert isinstance(first, ContextPack) and first.items == ()
        assert isinstance(delta, ContextPackDelta)
        assert apply_context_pack_delta(base, ContextPackDelta.from_bytes(delta.to_bytes())).items == ()

    asyncio.run(run())
