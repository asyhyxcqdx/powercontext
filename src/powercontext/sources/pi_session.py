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

"""Capture the visible evidence on a Pi v3 session branch with durable progress."""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, JsonValue

from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    ConnectorSubmissionStatus,
    Source,
    SourceDefinition,
    SourceMaterialization,
    TextEvidence,
)


class PiSessionInput(BaseModel):
    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    event: PiEventInput


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _event_identity(session_id: str, event_id: str) -> str:
    # Hash the structured pair to avoid separators, long IDs, and Unicode expansion.
    return "pi:" + hashlib.sha256(_canonical([session_id, event_id]).encode("utf-8")).hexdigest()


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")  # noqa: TRY003
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")  # noqa: TRY003


@dataclass(frozen=True)
class _Archive:
    session_id: str
    records: dict[str, dict[str, Any]]
    events: tuple[PiEventInput, ...]


def _read_archive(value: PiSessionInput) -> _Archive:
    # Split only actual JSONL record boundaries, not Unicode separators inside strings.
    records = [
        json.loads(line, parse_constant=_reject_constant)
        for line in value.content.decode("utf-8-sig").split("\n")
        if line.strip()
    ]
    if not records or not isinstance(records[0], dict):
        raise ValueError("Pi archive must start with a session header")  # noqa: TRY003
    header = records[0]
    if header.get("type") != "session" or type(header.get("version")) is not int or header["version"] != 3:
        raise ValueError("Pi archive must use session version 3")  # noqa: TRY003
    session_id = _nonempty_string(header.get("id"), "session id")
    nodes: dict[str, dict[str, Any]] = {}
    for record in records[1:]:
        if not isinstance(record, dict) or "parentId" not in record:
            raise ValueError("Pi event must be an object with parentId")  # noqa: TRY003
        event_id = _nonempty_string(record.get("id"), "event id")
        _nonempty_string(record.get("type"), "event type")
        parent = record["parentId"]
        if event_id in nodes or (parent is not None and (not isinstance(parent, str) or parent not in nodes)):
            raise ValueError("Pi events must have unique IDs and previously declared parents")  # noqa: TRY003
        nodes[event_id] = record
    leaf = value.leaf_id if value.leaf_id is not None else next(reversed(nodes), None)
    if leaf is not None and leaf not in nodes:
        raise ValueError("selected Pi leaf does not exist")  # noqa: TRY003
    branch = []
    while leaf is not None:
        record = nodes[leaf]
        branch.append(record)
        leaf = record["parentId"]
    events = tuple(event for record in reversed(branch) if (event := _visible_event(session_id, record)) is not None)
    return _Archive(session_id, nodes, events)


def _visible_blocks(value: object, *, tool_calls: bool = False) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if not isinstance(value, list):
        raise ValueError("Pi content must be a string or block array")  # noqa: TRY003, TRY004
    parts = []
    for block in value:
        if not isinstance(block, dict):
            raise ValueError("Pi content blocks must be objects")  # noqa: TRY003, TRY004
        if block.get("type") == "text":
            text = block.get("text")
            if not isinstance(text, str):
                raise ValueError("text blocks must contain a string")  # noqa: TRY003
            parts.append(text)
        elif tool_calls and block.get("type") == "toolCall":
            name = _nonempty_string(block.get("name"), "tool name")
            identity = _nonempty_string(block.get("id"), "tool call id")
            parts.append(f"[tool_call {name} {identity}] {_canonical(block.get('arguments', {}))}")
    return "\n".join(parts)


def _message_body(message: dict[str, Any], role: str) -> str:
    if role == "bashExecution":
        command, output = message.get("command", ""), message.get("output", "")
        if not isinstance(command, str) or not isinstance(output, str):
            raise ValueError("bash command and output must be strings")  # noqa: TRY003
        return f"$ {command}\n{output}" if command or output else ""
    body = _visible_blocks(message.get("content"), tool_calls=True)
    if role == "toolResult" and body:
        name = _nonempty_string(message.get("toolName"), "tool name")
        identity = _nonempty_string(message.get("toolCallId"), "tool call id")
        return f"[tool_result {name} {identity}] {body}"
    return body


def _visible_event(session_id: str, record: dict[str, Any]) -> PiEventInput | None:
    event_type = record["type"]
    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            raise ValueError("message event must contain a message object")  # noqa: TRY003
        role = _nonempty_string(message.get("role"), "message role")
        body = _message_body(message, role)
    elif event_type in {"compaction", "branch_summary"}:
        role, body = event_type, record.get("summary", "")
        if not isinstance(body, str):
            raise ValueError("Pi summaries must be strings")  # noqa: TRY003
    elif event_type == "custom_message":
        role, body = "custom", _visible_blocks(record.get("content"))
    else:
        return None
    if not body:
        return None
    return PiEventInput(
        session_id=session_id,
        event_id=record["id"],
        parent_id=record["parentId"],
        event_type=event_type,
        role=role,
        content=f"{role}: {body}",
        record=record,
    )


def parse_pi_session(value: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Validate the entire graph and return visible ancestors from root to leaf."""
    return _read_archive(value).events


class _PiEventAdapter:
    input_class = PiEventInput
    name = "pi-event"
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        return PiEventSource(
            name=_event_identity(value.session_id, value.event_id),
            materialization=SourceMaterialization.CAPTURED,
            event=value.model_copy(deep=True),
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return source.event.model_copy(deep=True)


class _PiEventTextProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type="pi-event",
            source_id=source.name,
            content=source.event.content,
            metadata=source.event.model_dump(include={"session_id", "event_id", "parent_id", "event_type", "role"}),
        )


PI_EVENT_SOURCE_DEFINITION: SourceDefinition[PiEventInput, PiEventSource, PiEventInput] = AdapterSourceDefinition(
    _PiEventAdapter(), projections=(_PiEventTextProjection(),)
)


class _Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    records: dict[str, str]


class PiSessionConnector:
    """Import new branch events; let ConnectorLifecycle commit progress last."""

    name = "pi-session-history"
    version = "1"
    source_definitions = frozenset({"pi-event"})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        archive = _read_archive(
            PiSessionInput(content=await asyncio.to_thread(self._path.read_bytes), leaf_id=self._leaf_id)
        )
        fingerprints = {
            identity: hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
            for identity, record in archive.records.items()
        }
        previous = (
            _Checkpoint(session_id=archive.session_id, records={})
            if session.checkpoint is None
            else _Checkpoint.model_validate(session.checkpoint)
        )
        if previous.session_id != archive.session_id or any(
            fingerprints.get(identity) != digest for identity, digest in previous.records.items()
        ):
            raise ValueError("previously imported Pi history has changed or disappeared")  # noqa: TRY003
        imported = dict(previous.records)
        for event in archive.events:
            if event.event_id in imported:
                continue
            outcome = await session.submit(_event_identity(event.session_id, event.event_id), "pi-event", event)
            if outcome.status is not ConnectorSubmissionStatus.ACCEPTED:
                return ConnectorRunCompletion(status=ConnectorRunStatus.INCOMPLETE, checkpoint=session.checkpoint)
            imported[event.event_id] = fingerprints[event.event_id]
        return ConnectorRunCompletion(
            status=ConnectorRunStatus.COMPLETE,
            checkpoint=_Checkpoint(session_id=archive.session_id, records=imported).model_dump(mode="json"),
        )


__all__ = ["PI_EVENT_SOURCE_DEFINITION", "PiEventInput", "PiSessionConnector", "PiSessionInput", "parse_pi_session"]
