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

"""Durable, scope-local evidence dependencies and replayable availability changes."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, update

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE as NODES
from powercontext.builtin.runtime.models import GetMemoryEntryRequest
from powercontext.builtin.sources import validate_scope_id
from powercontext.sources import SourceRef

if TYPE_CHECKING:
    from powercontext.builtin.runtime.application import BuiltinRuntime


class SourceLifecycleError(ValueError):
    """Invalid lifecycle identity, dependency, event or generation request."""

    def __init__(self, code: str) -> None:
        self.code = code
        messages = {
            "node-id": "node_id must be a nonblank string",
            "configuration": "Lifecycle persistence is not configured",
            "source-reference": "A SourceRef and positive integer revision are required",
            "memory-reference": "A MemoryCitation is required",
            "topic-reference": "A Topic Memory ArtifactRef is required",
            "policy": "policy must be all or any",
            "parents": "Derived nodes require at least one parent",
            "duplicate-parent": "Parents must be unique",
            "conflict": "Node identity is already bound differently",
            "parent-reference": "Parents must already exist and cannot include the node itself",
            "unreadable": "The registered reference must exist and be readable in this scope",
            "event": "A validated SourceLifecycleEvent is required",
            "event-source": "Unknown Source or mismatched lifecycle revision",
            "sequence": "Event sequence is stale or conflicts with an accepted event",
            "cycle": "Persisted dependencies contain a cycle",
            "binding": "Invalid persisted Memory binding",
            "body-version": "Registered Memory body version has changed",
            "purpose": "purpose must be generation or audit",
            "unknown": "Unknown lifecycle node",
            "unavailable": "Evidence is unavailable for generation",
        }
        super().__init__(messages.get(code, code))


class SourceLifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    node_id: str
    revision: int = Field(gt=0)
    sequence: int = Field(gt=0)
    available: bool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("node_id and reason must not be blank")  # noqa: TRY003
        return value


class _Binding(BaseModel):
    kind: Literal["source", "memory", "topic"]
    reference: SourceRef | MemoryCitation | ArtifactRef
    parents: tuple[str, ...] = ()
    policy: Literal["all", "any"] = "all"
    revision: int = 1


class _Node(BaseModel):
    node_id: str
    binding: _Binding
    available: bool
    sequence: int = 0
    event: SourceLifecycleEvent | None = None


def _node_key(node_id: str) -> str:
    if not isinstance(node_id, str) or not node_id.strip():
        raise SourceLifecycleError("node-id")
    return hashlib.sha256(node_id.encode("utf-8")).hexdigest()


class ScopedSourceLifecycle:
    """A single-writer DAG; desired state is durable before native state changes."""

    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None, scope_id: str) -> None:
        self._runtime = runtime
        self._database = database
        self.scope_id = validate_scope_id(scope_id)

    @property
    def database(self) -> AsyncDatabase:
        if self._database is None:
            raise SourceLifecycleError("configuration")
        return self._database

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int = 1) -> None:
        if not isinstance(source_ref, SourceRef) or type(revision) is not int or revision < 1:
            raise SourceLifecycleError("source-reference")
        await self._register(node_id, _Binding(kind="source", reference=source_ref, revision=revision))

    async def register_memory(
        self, node_id: str, citation: MemoryCitation, *, parents: tuple[str, ...], policy: str = "all"
    ) -> None:
        if not isinstance(citation, MemoryCitation):
            raise SourceLifecycleError("memory-reference")
        await self._register(node_id, self._derived_binding("memory", citation, parents, policy))

    async def register_topic(
        self, node_id: str, artifact_ref: ArtifactRef, *, parents: tuple[str, ...], policy: str = "all"
    ) -> None:
        if not isinstance(artifact_ref, ArtifactRef) or artifact_ref.family != "topic-memory":
            raise SourceLifecycleError("topic-reference")
        await self._register(node_id, self._derived_binding("topic", artifact_ref, parents, policy))

    @staticmethod
    def _derived_binding(
        kind: Literal["memory", "topic"], reference: MemoryCitation | ArtifactRef, parents: tuple[str, ...], policy: str
    ) -> _Binding:
        if not isinstance(policy, str) or policy not in {"all", "any"}:
            raise SourceLifecycleError("policy")
        if not isinstance(parents, (tuple, list)) or not parents:
            raise SourceLifecycleError("parents")
        for parent in parents:
            _node_key(parent)
        if len(set(parents)) != len(parents):
            raise SourceLifecycleError("duplicate-parent")
        return _Binding(
            kind=kind, reference=reference, parents=tuple(parents), policy="all" if policy == "all" else "any"
        )

    async def _register(self, node_id: str, binding: _Binding) -> None:
        key = _node_key(node_id)
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._read()
            if node_id in nodes:
                if nodes[node_id].binding != binding:
                    raise SourceLifecycleError("conflict")
                await self._reconcile_memory(nodes)
                return
            if node_id in binding.parents or any(parent not in nodes for parent in binding.parents):
                raise SourceLifecycleError("parent-reference")
            await self._validate_reference(binding.reference)
            available = True
            if binding.parents:
                support = [nodes[parent].available for parent in binding.parents]
                available = all(support) if binding.policy == "all" else any(support)
            node = _Node(node_id=node_id, binding=binding, available=available)
            reference = binding.reference
            artifact = reference.memory_ref if isinstance(reference, MemoryCitation) else reference
            async with self.database.transaction() as connection:
                await connection.execute(
                    insert(NODES).values(
                        scope_id=self.scope_id,
                        node_key=key,
                        node_id=node_id,
                        kind=binding.kind,
                        binding=binding.model_dump_json().encode("utf-8"),
                        available=available,
                        sequence=0,
                        artifact_id=artifact.artifact_id if isinstance(artifact, ArtifactRef) else None,
                        artifact_revision=artifact.revision if isinstance(artifact, ArtifactRef) else None,
                    )
                )
            nodes[node_id] = node
            # Registration is replayable too: if the native mutation fails, the
            # identical registration resumes from this persisted desired state.
            await self._reconcile_memory(nodes)

    async def _validate_reference(self, reference: SourceRef | MemoryCitation | ArtifactRef) -> None:
        records = self._runtime.records.for_scope(self.scope_id)
        try:
            if isinstance(reference, SourceRef):
                await records.get_source(reference.source_type, reference.source_id)
            elif isinstance(reference, MemoryCitation):
                await self._runtime.memory.for_scope(self.scope_id).get(GetMemoryEntryRequest(citation=reference))
            else:
                await records.get_artifact_revision(reference.family, reference.artifact_id, reference.revision)
        except (LookupError, ValueError) as error:
            raise SourceLifecycleError("unreadable") from error

    async def _read(self) -> dict[str, _Node]:
        async with self.database.transaction() as connection:
            rows = (await connection.execute(select(NODES).where(NODES.c.scope_id == self.scope_id))).mappings().all()
        return {
            row["node_id"]: _Node(
                node_id=row["node_id"],
                binding=_Binding.model_validate_json(row["binding"]),
                available=row["available"],
                sequence=row["sequence"],
                event=None if row["event"] is None else SourceLifecycleEvent.model_validate_json(row["event"]),
            )
            for row in rows
        }

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        if not isinstance(event, SourceLifecycleEvent):
            raise SourceLifecycleError("event")
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._read()
            source = nodes.get(event.node_id)
            if source is None or source.binding.kind != "source" or source.binding.revision != event.revision:
                raise SourceLifecycleError("event-source")
            if event.sequence < source.sequence or (event.sequence == source.sequence and source.event != event):
                raise SourceLifecycleError("sequence")
            if event.sequence > source.sequence:
                source.available = event.available
                source.sequence = event.sequence
                source.event = event
                remaining = {name for name, node in nodes.items() if node.binding.kind != "source"}
                visited = set(nodes) - remaining
                while remaining:
                    ready = sorted(name for name in remaining if set(nodes[name].binding.parents) <= visited)
                    if not ready:
                        raise SourceLifecycleError("cycle")
                    for name in ready:
                        node = nodes[name]
                        support = [nodes[parent].available for parent in node.binding.parents]
                        node.available = all(support) if node.binding.policy == "all" else any(support)
                    visited.update(ready)
                    remaining.difference_update(ready)
                async with self.database.transaction() as connection:
                    for name, node in nodes.items():
                        await connection.execute(
                            update(NODES)
                            .where(NODES.c.scope_id == self.scope_id, NODES.c.node_key == _node_key(name))
                            .values(
                                available=node.available,
                                sequence=node.sequence,
                                event=None if node.event is None else node.event.model_dump_json().encode("utf-8"),
                            )
                        )
            # Never mark a partially propagated event as finished. Re-read native
            # states on every replay; successful writes are skipped, failed writes retry.
            await self._reconcile_memory(nodes)
            return sorted(name for name, node in nodes.items() if node.available)

    async def _reconcile_memory(self, nodes: dict[str, _Node]) -> None:
        memories = [node for node in nodes.values() if node.binding.kind == "memory"]
        if not memories:
            return
        async with self._runtime._context(self.scope_id) as context:
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            entries = {entry.entry_id: entry for entry in await service.entries(current)}
            states = {entry.entry_id: entry.state for entry in current.content.manifest.entries}
            for node in memories:
                citation = node.binding.reference
                if not isinstance(citation, MemoryCitation):
                    raise SourceLifecycleError("binding")
                entry = entries.get(citation.entry_id)
                if entry is None or entry.entry_version_id != citation.entry_version_id:
                    raise SourceLifecycleError("body-version")
                desired = "active" if node.available else "inactive"
                if states[entry.entry_id] == desired:
                    continue
                mutate = service.reactivate if node.available else service.forget
                current = await mutate(current, entries=(entry,), reason="Source lifecycle propagation")
                states[entry.entry_id] = desired

    async def resolve(self, node_id: str, *, purpose: str = "generation") -> SourceRef | MemoryCitation | ArtifactRef:
        _node_key(node_id)
        if not isinstance(purpose, str) or purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("purpose")
        async with self._runtime._scope_operation(self.scope_id):
            node = (await self._read()).get(node_id)
            if node is None:
                raise SourceLifecycleError("unknown")
            if purpose == "generation" and not node.available:
                raise SourceLifecycleError("unavailable")
            return node.binding.reference


class SourceLifecycleApplication:
    def __init__(self, runtime: BuiltinRuntime, database: AsyncDatabase | None) -> None:
        self._runtime = runtime
        self._database = database

    def for_scope(self, scope_id: str) -> ScopedSourceLifecycle:
        return ScopedSourceLifecycle(self._runtime, self._database, scope_id)
