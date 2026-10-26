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

"""Preserve full Pi records and reject changes outside the currently selected branch."""

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from powercontext.sources import ConnectorBinding, SourceDefinitionRegistry, SourceRef
from powercontext.sources.connectors import ConnectorLifecycle
from powercontext.sources.pi_session import (
    PI_EVENT_SOURCE_DEFINITION,
    PiEventInput,
    PiSessionConnector,
    PiSessionInput,
    parse_pi_session,
)


def _content(records: list[dict[str, Any]]) -> bytes:
    header = {"type": "session", "version": 3, "id": "long-session:" + "海" * 300}
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in [header, *records]).encode()


def test_unicode_line_separator_and_large_result_survive_capture() -> None:
    body = "before\u2028after\u2029" + "evidence" * 5000
    records = [{"type": "message", "id": "event", "parentId": None, "message": {"role": "user", "content": body}}]
    event = parse_pi_session(PiSessionInput(content=_content(records)))[0]
    assert event.content == "user: " + body
    assert event.record == records[0]
    registry = SourceDefinitionRegistry((PI_EVENT_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(event))
    assert len(source.name) <= 256
    assert asyncio.run(registry.read(source)) == event
    event.record["mutated"] = True
    restored = asyncio.run(registry.read(source))
    assert isinstance(restored, PiEventInput)
    assert "mutated" not in restored.record


def test_mutation_of_previously_imported_other_branch_is_rejected(tmp_path: Path) -> None:
    class Checkpoints:
        checkpoint = None

        async def load(self, binding):
            return self.checkpoint

        async def save(self, binding, checkpoint, *, expected):
            assert self.checkpoint == expected
            self.checkpoint = json.loads(json.dumps(checkpoint))

    class Sink:
        async def submit(self, binding, item_id, definition_name, value):
            return SourceRef(source_type=definition_name, source_id=item_id)

    async def run() -> None:
        records = [
            {"type": "message", "id": "a", "parentId": None, "message": {"role": "user", "content": "root"}},
            {"type": "message", "id": "b", "parentId": "a", "message": {"role": "assistant", "content": "left"}},
            {"type": "message", "id": "c", "parentId": "a", "message": {"role": "assistant", "content": "right"}},
        ]
        path = tmp_path / "branches.jsonl"
        path.write_bytes(_content(records))
        checkpoints = Checkpoints()
        lifecycle = ConnectorLifecycle(sink=Sink(), checkpoints=checkpoints)
        binding = ConnectorBinding(
            scope_id="s", binding_id="b", connector_name="pi-session-history", connector_version="1"
        )
        imported = await lifecycle.run(PiSessionConnector(path, "b"), binding)
        records[1]["message"]["content"] = "rewritten left"
        path.write_bytes(_content(records))
        with pytest.raises(ValueError):
            await lifecycle.run(PiSessionConnector(path, "c"), binding)
        assert checkpoints.checkpoint == imported.committed_checkpoint
        records[1]["message"]["content"] = "left"
        path.write_bytes(_content(records))
        repaired = await lifecycle.run(PiSessionConnector(path, "c"), binding)
        assert len(repaired.items) == 1

    asyncio.run(run())
