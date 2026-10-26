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

"""Cancellation, independent failures and per-caller embedding usage."""

import asyncio

import pytest

from powercontext.builtin.artifacts.memory import EmbeddingProfile
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel


class _Provider:
    profile = EmbeddingProfile(profile_id="coalescing-test", model="offline", dimension=1)

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts: tuple[str, ...]) -> EmbeddingResult:
        self.calls.append(texts)
        self.started.set()
        await self.release.wait()
        if "broken" in texts:
            raise RuntimeError("provider failure")  # noqa: TRY003
        return EmbeddingResult(
            vectors=tuple((float(len(text)),) for text in texts),
            usage=InferenceUsage(requests=2, input_tokens=7, output_tokens=3),
        )


def test_late_waiter_joins_inflight_work_with_cache_disabled() -> None:
    async def run() -> None:
        provider = _Provider()
        model = CoalescingEmbeddingModel(provider, cache_size=0, coalesce_ms=0)
        first = asyncio.create_task(model.embed(("shared", "shared")))
        await provider.started.wait()
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        later = asyncio.create_task(model.embed(("shared",)))
        await asyncio.sleep(0)
        provider.release.set()
        result = await asyncio.wait_for(later, 2)
        assert result.vectors == ((6.0,),)
        assert result.usage == InferenceUsage(requests=2, input_tokens=7, output_tokens=3)
        assert provider.calls == [("shared",)]
        await model.embed(("shared",))
        assert provider.calls == [("shared",), ("shared",)]

    asyncio.run(run())


def test_failed_batch_does_not_fail_independent_waiters_or_successful_cache() -> None:
    async def run() -> None:
        provider = _Provider()
        model = CoalescingEmbeddingModel(provider, max_batch_size=1, coalesce_ms=0)
        failed = asyncio.create_task(model.embed(("broken", "safe")))
        survivor = asyncio.create_task(model.embed(("safe",)))
        await provider.started.wait()
        provider.release.set()
        with pytest.raises(RuntimeError, match="provider failure"):
            await asyncio.wait_for(failed, 2)
        assert (await asyncio.wait_for(survivor, 2)).vectors == ((4.0,),)
        cached = await model.embed(("safe",))
        assert cached.usage.requests == 0
        with pytest.raises(RuntimeError):
            await model.embed(("broken",))
        assert provider.calls.count(("safe",)) == 1
        assert provider.calls.count(("broken",)) == 2

    asyncio.run(run())


def test_each_call_counts_only_its_distinct_provider_batches() -> None:
    async def run() -> None:
        provider = _Provider()
        model = CoalescingEmbeddingModel(provider, max_batch_size=2, coalesce_ms=0)
        provider.release.set()
        wide, narrow = await asyncio.gather(model.embed(("a", "bb", "ccc", "a")), model.embed(("bb", "a")))
        assert wide.vectors == ((1.0,), (2.0,), (3.0,), (1.0,))
        assert wide.usage == InferenceUsage(requests=4, input_tokens=14, output_tokens=6)
        assert narrow.usage == InferenceUsage(requests=2, input_tokens=7, output_tokens=3)
        assert model.profile == provider.profile

    asyncio.run(run())
