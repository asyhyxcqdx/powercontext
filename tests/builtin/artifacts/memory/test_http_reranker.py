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

"""Response validation and transport failures through the public reranker."""

import asyncio
import json
from typing import Any

import httpx
import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory.http_reranker import HTTPMemoryReranker
from powercontext.builtin.artifacts.memory.models import MemoryHit


def _candidate() -> MemoryHit:
    return MemoryHit(
        memory_ref=ArtifactRef(family="memory", artifact_id="m", revision=1),
        entry_id="e",
        entry_version_id="v",
        text="complete candidate",
        score=1.0,
        matched_by=("fts",),
    )


@pytest.mark.parametrize(
    "item",
    [
        {"rank": True, "score": 1},
        {"rank": "1", "score": 1},
        {"rank": 1.0, "score": 1},
        {"rank": 1, "score": True},
        {"rank": 1, "score": "0.5"},
        {"rank": 1, "score": None},
    ],
)
def test_response_numbers_are_not_coerced(item: dict[str, Any]) -> None:
    async def run() -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"scores": [item]}))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://local.invalid", client=client).rerank("q", (_candidate(),), 1)

    asyncio.run(run())


@pytest.mark.parametrize("status", [301, 400, 503])
def test_non_success_status_preserves_httpx_error(status: int) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status))) as client:
            with pytest.raises(httpx.HTTPStatusError) as failure:
                await HTTPMemoryReranker("https://local.invalid", client=client).rerank("q", (_candidate(),), 1)
            assert failure.value.response.status_code == status
            assert not client.is_closed

    asyncio.run(run())


def test_later_batch_cannot_reuse_an_earlier_rank() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        rank = body["candidates"][0]["rank"]
        return httpx.Response(200, json={"scores": [{"rank": 1, "score": rank}]})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://local.invalid", client=client, batch_size=1).rerank(
                    "q", (_candidate(), _candidate()), 2
                )

    asyncio.run(run())
