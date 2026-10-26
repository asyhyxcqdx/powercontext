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

"""Availability recovery through actual runtime persistence and native Memory writes."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.artifacts.memory.service import MemoryService
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    CaptureSource,
    RememberMemoryRequest,
    SearchMemoryRequest,
    open_builtin_runtime,
)
from powercontext.builtin.runtime.source_lifecycle import SourceLifecycleError, SourceLifecycleEvent
from powercontext.builtin.scope import ScopeDraft


def test_interrupted_propagation_resumes_after_restart_without_rewriting_bodies(tmp_path, monkeypatch):
    async def run():
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'recovery.db'}"))
        event = SourceLifecycleEvent(node_id="source", revision=1, sequence=1, available=False, reason="withdrawn")
        references = []
        async with open_builtin_runtime(config) as runtime:
            assert runtime.scopes is not None
            scope = await runtime.scopes.create(ScopeDraft(title="Recovery", summary="Evidence", idempotency_key="r"))
            service = runtime.lifecycle.for_scope(scope.scope_id)
            receipt = await runtime.sources.for_scope(scope.scope_id).capture(
                CaptureSource(source_id="root", content="origin", metadata={})
            )
            await service.register_source("source", receipt.source_ref)
            memory = runtime.memory.for_scope(scope.scope_id)
            for number in range(3):
                result = await memory.remember(
                    RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text=f"Evidence {number}"),))
                )
                assert result.entry is not None
                references.append(result.entry.citation)
                await service.register_memory(f"entry{number}", result.entry.citation, parents=("source",))
            original_forget = MemoryService.forget
            calls = 0

            async def interrupted(self, *args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("interrupted")
                return await original_forget(self, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(MemoryService, "forget", interrupted)
                with pytest.raises(OSError, match="interrupted"):
                    await service.apply(event)
            partial = await memory.list(include_inactive=True)
            assert sum(record.state == "inactive" for record in partial.entries) == 1
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            service = runtime.lifecycle.for_scope(scope.scope_id)
            assert await service.apply(event) == []
            before = await memory.list(include_inactive=True)
            assert all(record.state == "inactive" for record in before.entries)
            await service.apply(event)
            assert (await memory.list(include_inactive=True)).memory_ref == before.memory_ref
            assert not (await memory.search(SearchMemoryRequest(query="Evidence", mode="fts"))).hits
            await service.apply(event.model_copy(update={"sequence": 2, "available": True}))
            after = await memory.list()
            assert {record.entry.entry_version_id for record in after.entries} == {
                ref.entry_version_id for ref in references
            }
            for number, reference in enumerate(references):
                assert await service.resolve(f"entry{number}") == reference

    asyncio.run(run())


def test_scope_identity_registration_and_event_replay_are_isolated():
    async def run():
        async with open_builtin_runtime(BuiltinConfig()) as runtime:
            assert runtime.scopes is not None
            services = []
            for identity in ("left", "right"):
                scope = await runtime.scopes.create(
                    ScopeDraft(title=identity, summary="Scope", idempotency_key=identity)
                )
                service = runtime.lifecycle.for_scope(scope.scope_id)
                receipt = await runtime.sources.for_scope(scope.scope_id).capture(
                    CaptureSource(source_id="same", content="same text", metadata={})
                )
                await service.register_source("same", receipt.source_ref, revision=3)
                await service.register_source("same", receipt.source_ref, revision=3)
                services.append(service)
            event = SourceLifecycleEvent(node_id="same", revision=3, sequence=1, available=False, reason="withdrawal")
            assert await services[0].apply(event) == []
            with pytest.raises(SourceLifecycleError):
                await services[0].resolve("same")
            assert await services[1].resolve("same") == receipt.source_ref
            with pytest.raises(SourceLifecycleError):
                await services[0].apply(event.model_copy(update={"reason": "different replay"}))
            with pytest.raises(SourceLifecycleError):
                await services[1].resolve("same", purpose="unknown")

    asyncio.run(run())


@pytest.mark.parametrize(
    "field,value", [("revision", True), ("sequence", 1.0), ("available", 1), ("node_id", 123), ("reason", " ")]
)
def test_event_rejects_coercion(field, value):
    payload = {"node_id": "root", "revision": 1, "sequence": 1, "available": True, "reason": "restored"}
    payload[field] = value
    with pytest.raises(ValidationError):
        SourceLifecycleEvent.model_validate(payload)
