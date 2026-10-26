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

"""Retrieve financial evidence, not just valid citations, through persisted Memory."""

from __future__ import annotations

import asyncio
import hashlib

from powercontext.builtin.artifacts.memory import MemoryCandidateRequest, MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    GetMemoryEntryRequest,
    SubmitSourceObservation,
    open_builtin_runtime,
)
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    SourceDefinitionRegistry,
    SourceObservation,
    manifest_for_definition,
    project_source_for_transport,
)
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION, PDFPageInput, search_pdf_pages


class _PagePipeline:
    async def extract(self, request: MemoryCandidateRequest, /) -> tuple[MemoryEntryInput, ...]:
        entries = []
        for source in request.sources:
            if isinstance(source, SourceObservation):
                projection = source.projection(TEXT_EVIDENCE_PROJECTION_KEY)
                assert isinstance(projection, dict)
                content = projection["content"]
                assert isinstance(content, str)
                entries.append(MemoryEntryInput(kind="page", text=content, sources=(source,)))
        return tuple(entries)


async def _capture(runtime, pages):
    assert runtime.scopes is not None
    scope = await runtime.scopes.create(
        ScopeDraft(title="Reports", summary="Financial evidence", idempotency_key="pdf")
    )
    registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
    await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
    identities = {}
    for document, number, body in pages:
        page = PDFPageInput(
            document_id=document,
            document_sha256=hashlib.sha256(document.encode()).hexdigest(),
            page_number=number,
            text=body,
        )
        observation = project_source_for_transport(registry, await registry.resolve(page))
        await runtime.ingestion.submit(SubmitSourceObservation(scope_id=scope.scope_id, observation=observation))
        identities[observation.name] = (document, number)
    while (await runtime.memory.for_scope(scope.scope_id).flush()).processed:
        pass
    return scope.scope_id, identities


def test_multiple_statement_requirements_survive_verbose_management_discussion_and_restart(tmp_path):
    async def run():
        document = "R7_2031_10K"
        pages = [
            (
                document,
                1,
                "CONSOLIDATED STATEMENTS OF INCOME\n2031 2030\nRevenue 900 800\nOperating profit 140 120\nNet income 95 80",
            ),
            (
                document,
                2,
                "CONSOLIDATED STATEMENT OF CASH FLOWS\n2031 2030\nDepreciation and amortization 30 20\nCapital expenditure 45 40",
            ),
        ]
        discussion = "Management discussion of consolidated statements, net revenue, earnings and operations: EBITDA, operating income, depreciation and amortization, cash flow statement and income statement trends include investment analyst estimates. "
        pages.extend((document, number + 3, discussion * 6 + f" Scenario {number}.") for number in range(35))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'reports.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(
                memory,
                "For R7 in FY2031, calculate EBITDA using operating income and depreciation from the statement of cash flows and income statement.",
                limit=20,
            )
            locations = []
            for citation in citations:
                entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                locations.append(identities[entry.sources[0].source_id])
            assert (document, 1) in locations and (document, 2) in locations
            assert len(locations) == len(set(locations)) <= 20

    asyncio.run(run())


def test_short_alphanumeric_company_id_keeps_the_requested_company():
    async def run():
        pages = [
            ("R7_2031_10K", 1, "CONSOLIDATED STATEMENT OF INCOME\nNet revenue 800\nOperating profit 100\n2031"),
            (
                "OTHER_2031_10K",
                1,
                "CONSOLIDATED STATEMENT OF INCOME\nR7 net revenue operating income operating profit net income income statement. "
                * 6,
            ),
        ]
        async with open_builtin_runtime(BuiltinConfig(), candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(memory, "What was R7's operating income in 2031?", limit=1)
            assert len(citations) == 1
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert identities[entry.sources[0].source_id][0] == "R7_2031_10K"

    asyncio.run(run())
