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
import io

import pytest
from pypdf import PdfWriter

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
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    PDFPageInput,
    parse_pdf_document,
    search_pdf_pages,
)


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


@pytest.mark.parametrize("document", ["NORTHSTAR_2031_10K", "NORTHSTAR_INC_2031_10K"])
def test_wrapped_statement_heading_and_legal_company_suffix(tmp_path, document):
    async def run():
        pages = [
            (document, 1, "CONSOLIDATED STATEMENTS\nOF CASH FLOWS\n2031 2030\nDepreciation 40 35"),
        ]
        discussion = "Northstar depreciation cash flow statement operating income earnings " * 15
        pages.extend(("OTHER_2031_10K", n + 2, discussion + str(n)) for n in range(25))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'wrapped.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(
                memory, "Northstar depreciation in the cash flow statement in 2031", limit=1
            )
            assert len(citations) == 1
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert identities[entry.sources[0].source_id] == (document, 1)

    asyncio.run(run())


def test_wrapped_heading_survives_discussion_from_same_company(tmp_path):
    async def run():
        document = "R7_2031_10K"
        pages = [(document, 1, "CONSOLIDATED STATEMENTS\nOF CASH FLOWS\nDepreciation 40 35")]
        discussion = "Discussion of cash flow statement and depreciation: investment analyst estimates. " * 15
        pages.extend((document, n + 2, discussion + str(n)) for n in range(25))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'discussion.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(memory, "R7 depreciation in the statement of cash flows", limit=1)
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert identities[entry.sources[0].source_id] == (document, 1)

    asyncio.run(run())


def test_long_statement_survives_a_saturated_candidate_pool(tmp_path):
    async def run():
        document = "R7_2031_10K"
        statement = (
            "CONSOLIDATED STATEMENTS OF CASH FLOWS\nDepreciation 40 35\n" + "Additional accounting information. " * 800
        )
        pages = [(document, 1, statement)]
        discussion = "Discussion of consolidated statements of cash flows and depreciation for R7. " * 20
        pages.extend((document, n + 2, discussion + str(n)) for n in range(270))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'saturated.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(memory, "R7 depreciation in the statement of cash flows", limit=1)
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert identities[entry.sources[0].source_id] == (document, 1)

    asyncio.run(run())


@pytest.mark.parametrize(
    "body", ["Financial detail 1234. " * 700, "Revenue from cafe\u0301 operations 1234"], ids=["long-page", "unicode"]
)
def test_full_page_text_is_preserved_after_restart(tmp_path, body):
    async def run():
        document = "COMPANY_2031_10K"
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'full-page.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, [(document, 1, body)])
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(memory, "1234", limit=20)
            assert len(citations) == 1
            entry = (await memory.get(GetMemoryEntryRequest(citation=citations[0]))).entry
            assert entry.text == f"{document}\n{body}".strip()
            assert identities[entry.sources[0].source_id] == (document, 1)

    asyncio.run(run())


def test_revised_blank_pages_keep_old_citations_and_scope_after_restart(tmp_path):
    async def run():
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=200)
        documents = []
        for title in ("Original", "Revised"):
            writer.add_metadata({"/Title": title})
            buffer = io.BytesIO()
            writer.write(buffer)
            documents.append(parse_pdf_document(PDFDocumentInput(document_id="R7", content=buffer.getvalue()))[0])
        assert documents[0].document_sha256 != documents[1].document_sha256
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        observations = [project_source_for_transport(registry, await registry.resolve(page)) for page in documents]
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'revisions.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope = await runtime.scopes.create(
                ScopeDraft(title="Reports", summary="Revisions", idempotency_key="reports")
            )
            other = await runtime.scopes.create(ScopeDraft(title="Other", summary="Isolated", idempotency_key="other"))
            await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
            memory = runtime.memory.for_scope(scope.scope_id)
            await runtime.ingestion.submit(
                SubmitSourceObservation(scope_id=scope.scope_id, observation=observations[0])
            )
            while (await memory.flush()).processed:
                pass
            old = (await search_pdf_pages(memory, "R7", limit=20))[0]
            old_entry = (await memory.get(GetMemoryEntryRequest(citation=old))).entry
            # Retry the original observation and add a distinct PDF revision.
            for observation in observations:
                await runtime.ingestion.submit(
                    SubmitSourceObservation(scope_id=scope.scope_id, observation=observation)
                )
            while (await memory.flush()).processed:
                pass
            outsider = documents[0].model_copy(update={"document_id": "R7-other-scope"})
            observation = project_source_for_transport(registry, await registry.resolve(outsider))
            await runtime.ingestion.submit(SubmitSourceObservation(scope_id=other.scope_id, observation=observation))
            while (await runtime.memory.for_scope(other.scope_id).flush()).processed:
                pass
        async with open_builtin_runtime(config) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            assert (await memory.get(GetMemoryEntryRequest(citation=old))).entry == old_entry
            for limit in (1, 2, 20):
                citations = await search_pdf_pages(memory, "R7", limit=limit)
                assert len(citations) == min(limit, 2)
                locations = set()
                for citation in citations:
                    entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                    assert entry.text == "R7"
                    locations.add(entry.sources[0].source_id)
                assert len(locations) == len(citations)
                assert locations <= {observation.name for observation in observations}

    asyncio.run(run())


@pytest.mark.parametrize(
    ("question", "required"),
    [
        ("Is Atlas a capital-intensive business?", {1, 2, 3}),
        ("How has Atlas's operating margin changed?", {1}),
        ("How has Atlas's free cashflow conversion changed?", {1, 3}),
    ],
)
def test_financial_concepts_retrieve_complementary_statements(tmp_path, question, required):
    async def run():
        document = "ATLAS_2031_10K"
        pages = [
            (
                document,
                1,
                "CONSOLIDATED STATEMENT OF INCOME\nRevenue 900 800\nOperating income 90 70\nNet income 50 40",
            ),
            (document, 2, "CONSOLIDATED BALANCE SHEET\nAssets 700 600\nProperty plant equipment 400 350"),
            (
                document,
                3,
                "CONSOLIDATED STATEMENT OF CASH FLOWS\nOperating activities 80 70\nCapital expenditures 30 20",
            ),
        ]
        prose = "Management discussion: capital-intensive operating margin and free cashflow conversion changed. " * 12
        pages.extend((document, i + 4, prose + str(i)) for i in range(30))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'concepts.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
            memory = runtime.memory.for_scope(scope)
            found = set()
            for citation in await search_pdf_pages(memory, question, limit=20):
                entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                found.add(identities[entry.sources[0].source_id][1])
            assert required <= found

    asyncio.run(run())


def test_exchange_symbol_is_derived_from_the_document_identity(tmp_path):
    async def run():
        document = "LUMEN_ANALYTICS_2031_10K"
        overview = "Item 1. Business.\nLumen Analytics (NASDAQ: LMX) provides subscription research services."
        pages = [(document, 1, overview)]
        discussion = (
            "CONSOLIDATED STATEMENT OF INCOME\nLMX gross margins historically consistent relevant metric company " * 12
        )
        pages.extend(("OTHER_2031_10K", i + 2, discussion + str(i)) for i in range(25))
        config = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'symbols.db'}"))
        async with open_builtin_runtime(config, candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
            memory = runtime.memory.for_scope(scope)
            found = []
            for citation in await search_pdf_pages(memory, "Is gross margin a relevant metric for LMX?", limit=20):
                entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                found.append(identities[entry.sources[0].source_id])
            assert (document, 1) in found

    asyncio.run(run())


@pytest.mark.parametrize(
    ("question", "evidence"),
    [
        ("Who are Zephyr's customers?", "Our principal clients are regional airlines."),
        (
            "How did Zephyr's effective tax rate change?",
            "TABLE 2: SUMMARY OF FINANCIAL PERFORMANCE\nEffective tax rate 18% 22%",
        ),
        (
            "Which Zephyr product categories account for revenue?",
            "Summary of Business Segment Data\nAircraft sales 700\nServices 300",
        ),
    ],
)
def test_concepts_retrieve_short_evidence_without_repeated_company_name(question, evidence):
    async def run():
        document = "ZEPHYR_2031_10K"
        pages = [(document, 1, evidence)]
        pages.extend(
            (document, n + 2, "Zephyr " * 40 + "customer service tax revenue report " * 12 + str(n)) for n in range(25)
        )
        async with open_builtin_runtime(BuiltinConfig(), candidate_pipeline=_PagePipeline()) as runtime:
            scope, identities = await _capture(runtime, pages)
            memory = runtime.memory.for_scope(scope)
            citations = await search_pdf_pages(memory, question, limit=20)
            found = []
            for citation in citations:
                entry = (await memory.get(GetMemoryEntryRequest(citation=citation))).entry
                found.append(identities[entry.sources[0].source_id])
            assert (document, 1) in found

    asyncio.run(run())
