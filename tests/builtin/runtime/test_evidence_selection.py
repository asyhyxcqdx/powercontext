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

from __future__ import annotations

import json

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.builtin.runtime import PrepareContextRequest
from powercontext.builtin.runtime.prepared_context import PreparedContextBuilder, PreparedMemoryCandidates


def _candidates(scope, text):
    ref = ArtifactRef(family="memory", artifact_id="memory", revision=3)
    hit = MemoryHit(
        memory_ref=ref, entry_id="entry", entry_version_id="version", text=text, score=1, matched_by=("fts",)
    )
    return PreparedMemoryCandidates(scope_id=scope, memory_ref=ref, hits=(hit, hit))


def test_same_text_across_scopes_keeps_distinct_exact_origins():
    text = "The cobalt sensor measures ocean temperature."
    request = PrepareContextRequest(query="cobalt sensor", max_bytes=1800, evidence_selection=True)
    build = PreparedContextBuilder().build_scopes_result(
        request=request,
        current_scope_id="left",
        memory_candidates=(_candidates("left", text), _candidates("right", text)),
    )
    assert len(build.fragments) == 2
    assert {fragment.address.memory.scope_id for fragment in build.fragments} == {"left", "right"}
    assert build.origins == tuple(fragment.address for fragment in build.fragments)
    assert build.context.content is not None
    assert build.context.content_bytes == len(build.context.content.encode()) <= request.max_bytes


def test_separated_evidence_preserves_offsets_and_avoids_irrelevant_middle():
    first = "The cobalt sensor calibration is 37 degrees."
    last = "The amber valve threshold is 19 degrees."
    text = first + " " + "General administrative notes. " * 100 + last
    request = PrepareContextRequest(query="cobalt calibration amber threshold", max_bytes=1400, evidence_selection=True)
    build = PreparedContextBuilder().build_scopes_result(
        request=request, current_scope_id="s", memory_candidates=(_candidates("s", text),)
    )
    assert [fragment.text for fragment in build.fragments] == [first, last]
    assert build.context.content is not None
    items = json.loads(build.context.content.splitlines()[-2])["items"]
    for item, fragment in zip(items, build.fragments, strict=True):
        assert item["content"] == text[fragment.start : fragment.end]
        assert item["start"] == fragment.start and item["end"] == fragment.end


def test_tiny_budget_and_oversized_unicode_sentence_are_exact():
    text = "海水背景 " * 200 + "cobalt sensor calibrated at 37 degrees " + "观测记录 " * 200
    builder = PreparedContextBuilder()
    for budget in (512, 650, 1200):
        request = PrepareContextRequest(query="cobalt sensor", max_bytes=budget, evidence_selection=True)
        result = builder.build_scopes_result(
            request=request, current_scope_id="s", memory_candidates=(_candidates("s", text),)
        )
        assert result.context.content_bytes <= budget
        for fragment in result.fragments:
            assert fragment.text == text[fragment.start : fragment.end]
        if budget == 1200:
            assert "cobalt sensor" in (result.context.content or "")
