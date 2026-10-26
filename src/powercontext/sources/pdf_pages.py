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

"""Capture all physical PDF pages and retrieve exact, persisted page evidence."""

from __future__ import annotations

import hashlib
import io
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

from powercontext.artifacts import MemoryCitation
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    Source,
    SourceDefinition,
    SourceMaterialization,
    TextEvidence,
)
from powercontext.sources._pdf_search import PDFSearchQuery, plan_pdf_query, rank_pdf_candidates

if TYPE_CHECKING:
    from powercontext.builtin.artifacts.memory import MemoryHit
    from powercontext.builtin.runtime.application import ScopedMemoryApplication


class PDFDocumentInput(BaseModel):
    document_id: str
    content: bytes

    @field_validator("document_id")
    @classmethod
    def nonblank_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")  # noqa: TRY003
        return value


class PDFPageInput(BaseModel):
    document_id: str
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(gt=0, strict=True)
    text: str

    @field_validator("document_id")
    @classmethod
    def nonblank_document(cls, value: str) -> str:
        return PDFDocumentInput.nonblank_document(value)


class PDFPageSource(Source):
    page: PDFPageInput


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Materialize every page before returning, including empty physical pages."""

    from pypdf import PdfReader

    from powercontext.sources._pdf_text import extract_page_text

    if not value.content.startswith(b"%PDF-") or b"%%EOF" not in value.content[-1024:]:
        raise ValueError("Incomplete or invalid PDF document")  # noqa: TRY003
    digest = hashlib.sha256(value.content).hexdigest()
    try:
        reader = PdfReader(io.BytesIO(value.content), strict=True)
        if reader.is_encrypted:
            reader.decrypt("")
        return tuple(
            PDFPageInput(
                document_id=value.document_id,
                document_sha256=digest,
                page_number=number,
                text=extract_page_text(page, reader),
            )
            for number, page in enumerate(reader.pages, 1)
        )
    except Exception as error:
        raise ValueError("Unable to parse the complete PDF document") from error  # noqa: TRY003


class _PDFPageAdapter:
    input_class = PDFPageInput
    source_class = PDFPageSource
    name = "pdf-page"

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        identity = json.dumps(
            [value.document_id, value.document_sha256, value.page_number], ensure_ascii=False, separators=(",", ":")
        )
        return PDFPageSource(
            name="pdf:" + hashlib.sha256(identity.encode()).hexdigest(),
            materialization=SourceMaterialization.CAPTURED,
            page=value,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return source.page


class _PDFPageProjection:
    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        page = source.page
        return TextEvidence(
            source_type="pdf-page",
            source_id=source.name,
            content=f"{page.document_id}\n{page.text}",
            metadata={
                "document_id": page.document_id,
                "document_sha256": page.document_sha256,
                "page_number": page.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION: SourceDefinition[PDFPageInput, PDFPageSource, PDFPageInput] = AdapterSourceDefinition(
    _PDFPageAdapter(), projections=(_PDFPageProjection(),)
)


async def search_pdf_pages(
    memory: ScopedMemoryApplication, question: str, limit: int = 10
) -> tuple[MemoryCitation, ...]:
    """Search the scoped index, then rank full-page and local-passage evidence offline."""

    from powercontext.builtin.runtime.models import GetMemoryEntryRequest

    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")  # noqa: TRY003
    if not question.strip():
        return ()
    query = plan_pdf_query(question)
    hits = await _retrieve_candidates(memory, query, limit)
    ordered = rank_pdf_candidates(hits, query, limit)
    selected: list[MemoryCitation] = []
    seen_pages: set[str] = set()
    for index in ordered:
        hit = hits[index]
        citation = MemoryCitation(
            memory_ref=hit.memory_ref, entry_id=hit.entry_id, entry_version_id=hit.entry_version_id
        )
        record = await memory.get(GetMemoryEntryRequest(citation=citation))
        source_ids = {source.source_id for source in record.entry.sources if source.source_id.startswith("pdf:")}
        if not source_ids or seen_pages & source_ids:
            continue
        seen_pages.update(source_ids)
        selected.append(citation)
        if len(selected) == limit:
            break
    return tuple(selected)


async def _retrieve_candidates(memory: ScopedMemoryApplication, query: PDFSearchQuery, limit: int) -> list[MemoryHit]:
    from powercontext.builtin.runtime.models import SearchMemoryRequest

    candidates = {}
    for probe in query.probes:
        page = await memory.search(SearchMemoryRequest(query=probe, mode="fts", limit=max(256, limit * 12)))
        for hit in page.hits:
            candidates.setdefault((hit.entry_id, hit.entry_version_id), hit)
    return list(candidates.values())
