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

"""Query-dependent selection of literal, scoped Memory evidence under a byte budget."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import pairwise

from powercontext._lexical import LexicalRanker, terms
from powercontext.artifacts import ArtifactAddress
from powercontext.builtin.runtime.errors import PreparedContextInvariantError
from powercontext.builtin.runtime.models import PrepareContextRequest, PreparedContext
from powercontext.builtin.runtime.prepared_context import (
    MemoryEntryAddress,
    PreparedContextBuild,
    PreparedEvidenceFragment,
    PreparedMemoryCandidates,
)
from powercontext.builtin.runtime.prepared_text import TRUST_POLICY


@dataclass(frozen=True)
class _Sentence:
    document: int
    start: int
    end: int


def _spans(text: str) -> tuple[tuple[int, int], ...]:
    # Decimal points and abbreviations without a following new sentence stay intact.
    boundaries = [
        0,
        *(match.end() for match in re.finditer(r"[.!?\u3002\uff01\uff1f](?:[\"')\]]*)\s+|\n\s*\n", text)),
        len(text),
    ]
    spans = []
    for start, end in pairwise(boundaries):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))
    return tuple(spans)


def _render(fragments: Sequence[PreparedEvidenceFragment]) -> str:
    items = [
        {
            "citation": {
                "scope_id": fragment.address.memory.scope_id,
                "memory_ref": fragment.address.memory.artifact.model_dump(mode="json"),
                "entry_id": fragment.address.entry_id,
                "entry_version_id": fragment.address.entry_version_id,
            },
            "content": fragment.text,
            "start": fragment.start,
            "end": fragment.end,
        }
        for fragment in fragments
    ]
    encoded = json.dumps({"trust": "untrusted_history", "items": items}, ensure_ascii=False, separators=(",", ":"))
    return f"{TRUST_POLICY}\n\nBEGIN_POWERCONTEXT_PREPARED_CONTEXT_V1\n{encoded}\nEND_POWERCONTEXT_PREPARED_CONTEXT_V1"


def _collect_candidates(groups: Sequence[PreparedMemoryCandidates]) -> tuple[list[str], list[MemoryEntryAddress]]:
    documents: list[str] = []
    addresses: list[MemoryEntryAddress] = []
    seen = set()
    for group in groups:
        for hit in group.hits:
            if group.memory_ref is None or hit.memory_ref != group.memory_ref:
                raise PreparedContextInvariantError("memory-ref-mismatch")
            address = MemoryEntryAddress(
                ArtifactAddress(scope_id=group.scope_id, artifact=hit.memory_ref), hit.entry_id, hit.entry_version_id
            )
            key = (
                group.scope_id,
                hit.memory_ref.artifact_id,
                hit.memory_ref.revision,
                hit.entry_id,
                hit.entry_version_id,
            )
            if key not in seen and hit.text.strip():
                seen.add(key)
                addresses.append(address)
                documents.append(hit.text)
    return documents, addresses


def _sentence_scores(documents: list[str], sentences: list[_Sentence], query: dict[str, float]) -> list[float]:
    texts = [documents[sentence.document][sentence.start : sentence.end] for sentence in sentences]
    ranker = LexicalRanker(texts)
    document_ranker = LexicalRanker(documents)
    document_scores = [document_ranker.score(index, query) for index in range(len(documents))]
    best_document = max(document_scores, default=0) or 1
    scores = []
    for index, sentence in enumerate(sentences):
        score = ranker.score(index, query)
        score *= 0.45 + 0.55 * document_scores[sentence.document] / best_document
        # Scientific findings and conclusions often state the tested relation;
        # this is a general sentence feature, independent of any dataset labels.
        if re.search(r"\b(results?|conclu\w*|show\w*|found|demonstrat\w*|suggest\w*|indicat\w*)\b", texts[index], re.I):
            score *= 1.12
        scores.append(score)

    return scores


def _fragments_for(
    selected: frozenset[int], *, documents: list[str], addresses: list[MemoryEntryAddress], sentences: list[_Sentence]
) -> tuple[PreparedEvidenceFragment, ...]:
    intervals: dict[int, list[tuple[int, int]]] = {}
    for index in sorted(selected):
        sentence = sentences[index]
        spans = intervals.setdefault(sentence.document, [])
        if spans and not documents[sentence.document][spans[-1][1] : sentence.start].strip():
            spans[-1] = (spans[-1][0], sentence.end)
        else:
            spans.append((sentence.start, sentence.end))
    return tuple(
        PreparedEvidenceFragment(addresses[document], start, end, documents[document][start:end])
        for document, spans in intervals.items()
        for start, end in spans
    )


def _beam_selection(
    scores: list[float], max_bytes: int, fragments_for: Callable[[frozenset[int]], tuple[PreparedEvidenceFragment, ...]]
) -> tuple[PreparedEvidenceFragment, ...]:
    # A small beam compares alternative sets instead of spending the entire budget
    # on the first hit. Adjacent selections merge, charging their citation only once.
    candidates = sorted((index for index, score in enumerate(scores) if score > 0), key=lambda i: (-scores[i], i))[:48]
    beam: dict[frozenset[int], float] = {frozenset(): 0.0}
    best: tuple[float, frozenset[int]] = (0.0, frozenset())
    for _ in range(8):
        expanded = dict(beam)
        for chosen, value in beam.items():
            for index in candidates:
                if index in chosen:
                    continue
                selection = chosen | {index}
                if selection in expanded:
                    continue
                fragments = fragments_for(selection)
                if len(_render(fragments).encode("utf-8")) > max_bytes:
                    continue
                score = value + scores[index]
                expanded[selection] = score
                if score > best[0]:
                    best = (score, selection)
        beam = dict(sorted(expanded.items(), key=lambda item: (-item[1], tuple(sorted(item[0]))))[:16])
        if expanded.keys() == {frozenset()}:
            break
    return fragments_for(best[1])


def _fit_window(
    sentence: _Sentence,
    documents: list[str],
    addresses: list[MemoryEntryAddress],
    query: dict[str, float],
    max_bytes: int,
) -> tuple[PreparedEvidenceFragment, ...]:
    fragments: tuple[PreparedEvidenceFragment, ...] = ()
    # One long sentence can exceed the budget. Keep a literal window around
    # its strongest query occurrence, never an invented or ellipsized snippet.
    text = documents[sentence.document]
    matches = [
        m for m in re.finditer(r"[^\W_]+", text[sentence.start : sentence.end]) if set(terms(m.group())) & query.keys()
    ]
    center = sentence.start + (matches[0].start() if matches else 0)
    low, high = 1, sentence.end - sentence.start
    while low <= high:
        width = (low + high) // 2
        start = max(sentence.start, min(center - width // 3, sentence.end - width))
        candidate = (
            PreparedEvidenceFragment(addresses[sentence.document], start, start + width, text[start : start + width]),
        )
        if len(_render(candidate).encode("utf-8")) <= max_bytes:
            fragments = candidate
            low = width + 1
        else:
            high = width - 1
    return fragments


def select_evidence(request: PrepareContextRequest, groups: Sequence[PreparedMemoryCandidates]) -> PreparedContextBuild:
    documents, addresses = _collect_candidates(groups)
    sentences = [
        _Sentence(index, start, end) for index, document in enumerate(documents) for start, end in _spans(document)
    ]
    query = dict.fromkeys(terms(request.query), 1.0)
    scores = _sentence_scores(documents, sentences, query)
    fragments_for = partial(_fragments_for, documents=documents, addresses=addresses, sentences=sentences)
    fragments = _beam_selection(scores, request.max_bytes, fragments_for)
    if not fragments and scores and max(scores) > 0:
        sentence = sentences[max(range(len(scores)), key=lambda index: scores[index])]
        fragments = _fit_window(sentence, documents, addresses, query, request.max_bytes)
    if not fragments:
        return PreparedContextBuild(context=PreparedContext(status="empty", content=None, content_bytes=0), origins=())
    content = _render(fragments)
    return PreparedContextBuild(
        context=PreparedContext(status="ready", content=content, content_bytes=len(content.encode("utf-8"))),
        origins=tuple(fragment.address for fragment in fragments),
        fragments=fragments,
    )
