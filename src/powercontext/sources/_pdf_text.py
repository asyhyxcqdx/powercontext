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

import zlib
from typing import TYPE_CHECKING

from pypdf import get_configuration
from pypdf.filters import decode_stream_data
from pypdf.generic import (
    ArrayObject,
    ContentStream,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    PdfObject,
    StreamObject,
)

from powercontext.sources._pdf_actual_text import restore_actual_text

if TYPE_CHECKING:
    from pypdf import PageObject, PdfReader


def extract_page_text(page: PageObject, reader: PdfReader) -> str:
    """Normalize only invisible cursor movements, preserving PDF glyph bytes."""

    contents = page.get("/Contents")
    if contents is None:
        return page.extract_text() or ""
    original_resources = page.get("/Resources")
    resources = _copy_resources(original_resources)
    normalized = _normalized_content(contents, resources, reader, set())
    page[NameObject("/Contents")] = normalized
    page[NameObject("/Resources")] = resources
    try:
        return page.extract_text() or ""
    finally:
        # Do not retain every page's parsed operator list for the whole report.
        page[NameObject("/Contents")] = contents
        if original_resources is None:
            del page["/Resources"]
        else:
            page[NameObject("/Resources")] = original_resources


def _copy_resources(value: PdfObject | None) -> DictionaryObject:
    original = value.get_object() if value is not None else None
    resources = DictionaryObject(original) if isinstance(original, DictionaryObject) else DictionaryObject()
    xobjects = resources.get("/XObject")
    xobjects = xobjects.get_object() if xobjects is not None else None
    if isinstance(xobjects, DictionaryObject):
        resources[NameObject("/XObject")] = DictionaryObject(xobjects)
    return resources


def _validate_compression(contents: PdfObject) -> None:
    source = contents.get_object()
    if isinstance(source, ArrayObject):
        for item in source:
            _validate_compression(item)
        return
    if not isinstance(source, StreamObject):
        return
    filters = source.get("/Filter")
    if filters is None:
        return
    filters = filters.get_object()
    filters = list(filters) if isinstance(filters, ArrayObject) else [filters]
    for index, filter_name in enumerate(filters):
        if filter_name not in {"/FlateDecode", "/Fl"}:
            continue
        # The base StreamObject method returns encoded bytes; the subclass's
        # decoder deliberately recovers truncated/corrupt deflate streams.
        data = StreamObject.get_data(source)
        if index:
            prefix = DecodedStreamObject()
            prefix.set_data(data)
            prefix[NameObject("/Filter")] = ArrayObject(filters[:index])
            parameters = source.get("/DecodeParms")
            if parameters is not None:
                prefix[NameObject("/DecodeParms")] = parameters.get_object()
            data = decode_stream_data(prefix)
        inflater = zlib.decompressobj()
        inflater.decompress(data, max_length=get_configuration().zlib_maximum_output_length)
        if not inflater.eof:
            raise ValueError("Incomplete or oversized PDF text stream")  # noqa: TRY003


def _normalized_content(
    contents: PdfObject,
    resources: DictionaryObject,
    reader: PdfReader,
    active_forms: set[int],
) -> ContentStream:
    # Keep encoded glyphs as bytes. Auto-decoding content strings here would
    # bypass the font's ToUnicode map when pypdf extracts the normalized stream.
    _validate_compression(contents)
    stream = ContentStream(contents, reader, forced_encoding="bytes")
    operations = list(stream.operations)
    xobjects = resources.get("/XObject")
    prepared_forms: set[str] = set()
    # pypdf's strict reader still accepts unbalanced text objects. Validate
    # the concatenated page contents (or an individual Form), not each
    # constituent stream: a legal text object can span a /Contents array.
    in_text_object = False
    for index, (operands, operator) in enumerate(operations):
        if operator == b"BT":
            if in_text_object:
                raise ValueError("Nested PDF text object")  # noqa: TRY003
            in_text_object = True
        elif operator == b"ET":
            if not in_text_object:
                raise ValueError("Unmatched PDF text object end")  # noqa: TRY003
            in_text_object = False
        if operator == b"TJ" and index + 1 < len(operations) and operations[index + 1][1] == b"ET":
            items = list(operands[0])
            # ET discards this text position. A trailing TJ adjustment moves no
            # visible glyph, but plain extraction incorrectly emits a space.
            while items and isinstance(items[-1], (int, float)):
                items.pop()
            operations[index] = ([ArrayObject(items)], operator)
        elif operator == b"Do" and isinstance(xobjects, DictionaryObject) and operands:
            name = str(operands[0])
            if name in prepared_forms:
                continue
            form = xobjects[operands[0]].get_object()
            if not isinstance(form, DictionaryObject) or form.get("/Subtype") != "/Form":
                continue
            identity = id(form)
            if identity in active_forms:
                raise ValueError("Recursive PDF form")  # noqa: TRY003
            replacement = DecodedStreamObject()
            replacement.update({
                key: value for key, value in form.items() if key not in {"/Length", "/Filter", "/DecodeParms"}
            })
            inherited = _copy_resources(form.get("/Resources", resources))
            replacement[NameObject("/Resources")] = inherited
            normalized = _normalized_content(form, inherited, reader, active_forms | {identity})
            replacement.set_data(normalized.get_data())
            xobjects[operands[0]] = replacement
            prepared_forms.add(name)
    if in_text_object:
        raise ValueError("Unterminated PDF text object")  # noqa: TRY003
    stream.operations = restore_actual_text(operations, resources)
    return stream
