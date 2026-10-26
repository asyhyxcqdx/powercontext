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

"""Extract text without treating discarded text-position adjustments as spaces."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pypdf.generic import ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject, NameObject, PdfObject

if TYPE_CHECKING:
    from pypdf import PageObject, PdfReader


def extract_page_text(page: PageObject, reader: PdfReader) -> str:
    """Normalize only invisible cursor movements, preserving PDF glyph bytes."""

    contents = page.get("/Contents")
    if contents is None:
        return page.extract_text() or ""
    page[NameObject("/Contents")] = _normalized_content(contents, page.get("/Resources"), reader, {})
    try:
        return page.extract_text() or ""
    finally:
        # Do not retain every page's parsed operator list for the whole report.
        page[NameObject("/Contents")] = contents


def _normalized_content(
    contents: PdfObject,
    resources: PdfObject | None,
    reader: PdfReader,
    forms: dict[int, DecodedStreamObject],
) -> ContentStream:
    # Keep encoded glyphs as bytes. Auto-decoding content strings here would
    # bypass the font's ToUnicode map when pypdf extracts the normalized stream.
    stream = ContentStream(contents, reader, forced_encoding="bytes")
    operations = list(stream.operations)
    resource_dict = resources.get_object() if resources is not None else None
    xobjects = resource_dict.get("/XObject") if isinstance(resource_dict, DictionaryObject) else None
    xobjects = xobjects.get_object() if xobjects is not None else None
    for index, (operands, operator) in enumerate(operations):
        if operator == b"TJ" and index + 1 < len(operations) and operations[index + 1][1] == b"ET":
            items = list(operands[0])
            # ET discards this text position. A trailing TJ adjustment moves no
            # visible glyph, but plain extraction incorrectly emits a space.
            while items and isinstance(items[-1], (int, float)):
                items.pop()
            operations[index] = ([ArrayObject(items)], operator)
        elif operator == b"Do" and isinstance(xobjects, DictionaryObject) and operands:
            form = xobjects[operands[0]].get_object()
            if not isinstance(form, DictionaryObject) or form.get("/Subtype") != "/Form":
                continue
            identity = id(form)
            if identity not in forms:
                replacement = DecodedStreamObject()
                replacement.update({
                    key: value for key, value in form.items() if key not in {"/Length", "/Filter", "/DecodeParms"}
                })
                forms[identity] = replacement
                normalized = _normalized_content(form, form.get("/Resources", resources), reader, forms)
                replacement.set_data(normalized.get_data())
            xobjects[operands[0]] = forms[identity]
    stream.operations = operations
    return stream
