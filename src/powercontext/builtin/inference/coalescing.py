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

"""Share in-flight embedding work and cache successful vectors per model."""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(frozen=True, slots=True)
class _CompletedEmbedding:
    vector: EmbeddingVector
    batch: object
    usage: InferenceUsage


def _observe_failure(future: asyncio.Future[_CompletedEmbedding]) -> None:
    # A cancelled last caller leaves the shared work running for late joiners.
    if not future.cancelled():
        future.exception()


class CoalescingEmbeddingModel:
    """Batch calls within one event loop without coupling caller cancellation."""

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size <= 0:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")  # noqa: TRY003
        if type(coalesce_ms) not in (int, float) or not math.isfinite(coalesce_ms) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be finite and non-negative")  # noqa: TRY003
        self.profile = model.profile
        self._model = model
        self._max_batch_size = max_batch_size
        self._delay = coalesce_ms / 1000
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._inflight: dict[str, asyncio.Future[_CompletedEmbedding]] = {}
        self._pending: dict[str, asyncio.Future[_CompletedEmbedding]] = {}
        self._dispatch_task: asyncio.Task[None] | None = None
        self._batches: set[asyncio.Task[None]] = set()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        vectors: dict[str, EmbeddingVector] = {}
        waiting: dict[str, asyncio.Future[_CompletedEmbedding]] = {}
        loop = asyncio.get_running_loop()
        for text in texts:
            if text in self._cache:
                self._cache.move_to_end(text)
                vectors[text] = self._cache[text]
            elif text not in waiting:
                future = self._inflight.get(text)
                if future is None:
                    future = loop.create_future()
                    future.add_done_callback(_observe_failure)
                    self._inflight[text] = self._pending[text] = future
                waiting[text] = future
        if self._pending and self._dispatch_task is None:
            self._dispatch_task = asyncio.create_task(self._dispatch())

        completed = await asyncio.gather(*(asyncio.shield(future) for future in waiting.values()))
        usage_by_batch: dict[object, InferenceUsage] = {}
        for text, result in zip(waiting, completed, strict=True):
            vectors[text] = result.vector
            usage_by_batch[result.batch] = result.usage
        usages = tuple(usage_by_batch.values())
        return EmbeddingResult(
            vectors=tuple(vectors[text] for text in texts),
            usage=InferenceUsage(
                requests=sum(usage.requests for usage in usages),
                input_tokens=(
                    sum(usage.input_tokens or 0 for usage in usages)
                    if any(usage.input_tokens is not None for usage in usages)
                    else None
                ),
                output_tokens=(
                    sum(usage.output_tokens or 0 for usage in usages)
                    if any(usage.output_tokens is not None for usage in usages)
                    else None
                ),
            ),
        )

    async def _dispatch(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            for text, future in self._pending.items():
                future.cancel()
                self._inflight.pop(text, None)
            self._pending.clear()
            raise
        finally:
            self._dispatch_task = None
        pending = tuple(self._pending.items())
        self._pending.clear()
        for start in range(0, len(pending), self._max_batch_size):
            task = asyncio.create_task(self._run_batch(pending[start : start + self._max_batch_size]))
            self._batches.add(task)
            task.add_done_callback(self._batches.discard)

    async def _run_batch(self, batch: tuple[tuple[str, asyncio.Future[_CompletedEmbedding]], ...]) -> None:
        try:
            result = await self._model.embed(tuple(text for text, _ in batch))
            if len(result.vectors) != len(batch):
                raise ValueError("embedding vector count must match the batch size")  # noqa: TRY003, TRY301
            identity = object()
            for (text, future), vector in zip(batch, result.vectors, strict=True):
                if self._cache_size:
                    self._cache[text] = vector
                    self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                future.set_result(_CompletedEmbedding(vector, identity, result.usage))
        except asyncio.CancelledError:
            for _, future in batch:
                future.cancel()
            raise
        except Exception as error:
            for _, future in batch:
                future.set_exception(error)
        finally:
            for text, _ in batch:
                self._inflight.pop(text, None)


__all__ = ["CoalescingEmbeddingModel"]
