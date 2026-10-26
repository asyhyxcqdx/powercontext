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
from collections import Counter

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)

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


def _positioned_text_document(*, form: bool) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Courier"),
    })
    cmap = DecodedStreamObject()
    cmap.set_data(
        b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap "
        b"1 begincodespacerange <00> <FF> endcodespacerange "
        b"2 beginbfchar <41> <4E2D> <42> <6587> endbfchar "
        b"endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    unicode_font = DictionaryObject(font)
    unicode_font[NameObject("/ToUnicode")] = cmap
    resources = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font, NameObject("/F2"): unicode_font})
    })
    operations = []
    for row, line in enumerate(("Revenue 2022 2021", "Operating income 1234 1111")):
        for column, character in enumerate(line):
            # The final cursor movement has no visible effect: ET ends the text
            # object, and the next BT starts again at an explicit position.
            operations.append(f"BT /F1 10 Tf {30 + 6 * column} {700 - 20 * row} Td [({character}) -2000] TJ ET")
    operations.extend([
        "BT /F1 10 Tf 30 640 Td [(Net) -600 (profit)] TJ ET",
        "BT /F1 10 Tf 30 620 Td [(Cash) -600] TJ (flow) Tj ET",
        "BT /F1 10 Tf 0 1 -1 0 550 80 Tm (Rotated total 789) Tj ET",
        "BT /F2 10 Tf 30 600 Td [(A) -2000] TJ ET",
        "BT /F2 10 Tf 36 600 Td [(B) -2000] TJ ET",
    ])
    content = DecodedStreamObject()
    content.set_data("\n".join(operations).encode())
    if form:
        content.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Form"),
            NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 600, 800)]),
            NameObject("/Resources"): resources,
        })
        resources = DictionaryObject({NameObject("/XObject"): DictionaryObject({NameObject("/Fm"): content})})
        content = DecodedStreamObject()
        content.set_data(b"q /Fm Do Q")
    page[NameObject("/Resources")] = resources
    page[NameObject("/Contents")] = content
    writer.add_blank_page(width=600, height=800)
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


@pytest.mark.parametrize("form", [False, True])
def test_character_positioning_preserves_words_numbers_and_unicode(form):
    pages = parse_pdf_document(PDFDocumentInput(document_id="positioned", content=_positioned_text_document(form=form)))
    assert len(pages) == 2 and pages[1].text == ""
    text = " ".join(pages[0].text.split())
    for expected in (
        "Revenue 2022 2021",
        "Operating income 1234 1111",
        "Net profit",
        "Cash flow",
        "Rotated total 789",
        "中文",
    ):
        assert expected in text
    expected_words = "Revenue 2022 2021 Operating income 1234 1111 Net profit Cash flow Rotated total 789 中文"
    assert Counter(re.findall(r"\w+", text)) == Counter(re.findall(r"\w+", expected_words))
