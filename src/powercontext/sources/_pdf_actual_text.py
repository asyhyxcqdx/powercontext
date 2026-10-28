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

"""Honor explicit Unicode replacements for individual PDF ligature glyphs."""

from __future__ import annotations

from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, create_string_object


def restore_actual_text(operations: list, resources: DictionaryObject) -> list:
    """Use document-supplied ActualText, keeping glyph widths and positioning.

    This handles single-glyph marked spans. Complex multi-glyph or nested
    spans keep their original mapping rather than guessing text boundaries.
    All font dictionaries are local copies; shared PDF objects stay intact.
    """
    original_fonts = resources.get("/Font")
    if original_fonts is None:
        return operations
    fonts = DictionaryObject(original_fonts.get_object())
    resources[NameObject("/Font")] = fonts
    font_state = None
    state_stack = []
    replacements = {}
    cache = {}
    for index, (operands, operator) in enumerate(operations):
        if operator == b"q":
            state_stack.append(font_state)
        elif operator == b"Q" and state_stack:
            font_state = state_stack.pop()
        elif operator == b"Tf":
            font_state = operands
        elif operator == b"BDC" and font_state is not None and len(operands) == 2:
            span = _single_glyph_span(operations, index, resources)
            if span is None:
                continue
            position, args, text = span
            code = args[0]
            font = fonts[font_state[0]].get_object()
            width = (
                2
                if font.get("/Subtype") == "/Type0" and font.get("/Encoding") in ("/Identity-H", "/Identity-V")
                else 1
                if font.get("/Subtype") in ("/Type1", "/TrueType")
                else 0
            )
            if not isinstance(code, bytes) or len(code) != width:
                continue
            key = (str(font_state[0]), code, text)
            if key not in cache:
                name = _replacement_font(fonts, font, code, text, width)
                cache[key] = name
            replacements[position] = ([cache[key], font_state[1]], list(font_state))
    return _apply_font_overrides(operations, replacements)


def _apply_font_overrides(operations, replacements):
    result = []
    for index, operation in enumerate(operations):
        replacement = replacements.get(index)
        if replacement is not None:
            result.append((replacement[0], b"Tf"))
        result.append(operation)
        if replacement is not None:
            result.append((replacement[1], b"Tf"))
    return result


def _single_glyph_span(operations, index, resources):
    properties = operations[index][0][1]
    if isinstance(properties, NameObject):
        named = resources.get("/Properties", DictionaryObject()).get_object()
        properties = named.get(properties)
    properties = properties.get_object() if hasattr(properties, "get_object") else properties
    if not isinstance(properties, DictionaryObject) or "/ActualText" not in properties:
        return None
    text = properties["/ActualText"]
    if isinstance(text, bytes):
        text = create_string_object(text)
    if not isinstance(text, str) or not text:
        return None
    end = index + 1
    while end < len(operations) and operations[end][1] not in (b"EMC", b"BDC", b"BMC"):
        end += 1
    if end == len(operations) or operations[end][1] != b"EMC":
        return None
    span = operations[index + 1 : end]
    if any(op in (b"Tf", b"BT", b"ET", b"q", b"Q") for _, op in span):
        return None
    shows = [(index + 1 + n, args, op) for n, (args, op) in enumerate(span) if op in (b"Tj", b"TJ", b"'", b'"')]
    if len(shows) != 1 or shows[0][2] != b"Tj":
        return None
    return shows[0][0], shows[0][1], text


def _replacement_font(fonts, font, code, text, width):
    name = NameObject("/ActualText" + str(len(fonts)))
    while name in fonts:
        name = NameObject(str(name) + "_")
    cmap = DecodedStreamObject()
    cmap.set_data(
        (
            "/CIDInit /ProcSet findresource begin 12 dict begin begincmap\n"
            "/CMapType 2 def\n1 begincodespacerange\n"
            f"<{'00' * width}> <{'ff' * width}>\nendcodespacerange\n"
            f"1 beginbfchar\n<{code.hex()}> <{text.encode('utf-16-be').hex()}>\n"
            "endbfchar\nendcmap\nend end"
        ).encode("ascii")
    )
    replacement = DictionaryObject(font)
    replacement[NameObject("/ToUnicode")] = cmap
    fonts[name] = replacement
    return name
