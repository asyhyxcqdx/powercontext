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

import asyncio
import io
import re

import pytest
from pypdf import PdfWriter

from powercontext.sources import SourceDefinitionRegistry
from powercontext.sources.pdf_pages import PDF_PAGE_SOURCE_DEFINITION, PDFDocumentInput, parse_pdf_document


def _document(*, encrypted=False):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if encrypted:
        writer.encrypt(user_password="required", owner_password="owner")  # noqa: S106 -- intentionally locked test PDF
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def test_damaged_cross_reference_and_password_required_fail_atomically():
    raw = _document()
    damaged = re.sub(rb"startxref\s+\d+", b"startxref\n99999999", raw)
    for content in (damaged, _document(encrypted=True)):
        with pytest.raises(ValueError):
            parse_pdf_document(PDFDocumentInput(document_id="corrupt", content=content))


def test_long_unicode_document_ids_have_bounded_distinct_page_identities():
    async def run():
        content = _document()
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        first = parse_pdf_document(PDFDocumentInput(document_id="报告" * 500, content=content))[0]
        second = first.model_copy(update={"document_id": first.document_id + ":2"})
        source = await registry.resolve(first)
        other = await registry.resolve(second)
        assert len(source.name) <= 256
        assert source.name != other.name
        assert await registry.read(source) == first

    asyncio.run(run())
