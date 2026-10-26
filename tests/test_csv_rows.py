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

"""CSV boundary cases complementing the public runtime acceptance scenario."""

import asyncio
import json
from urllib.parse import quote

import pytest

from powercontext.sources import TEXT_EVIDENCE_PROJECTION_KEY, SourceDefinitionRegistry, SourceMaterialization
from powercontext.sources.csv_rows import (
    CSV_ROW_SOURCE_DEFINITION,
    CSVDocumentInput,
    CSVRowInput,
    CSVRowSource,
    csv_row_source_id,
    parse_csv_document,
)


def test_unicode_row_round_trips_without_normalizing_fields() -> None:
    document_id = "机场:航班/%"
    rows = parse_csv_document(
        CSVDocumentInput(
            document_id=document_id,
            primary_key=" id ",
            content=' id ,数量,布尔,空值,备注\r\n 键%:/ ,0012,false,,"一\r二\n三\r\n四"\r\n'.encode(),
        )
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.columns == (" id ", "数量", "布尔", "空值", "备注")
    assert row.values == (" 键%:/ ", "0012", "false", "", "一\r二\n三\r\n四")
    registry = SourceDefinitionRegistry((CSV_ROW_SOURCE_DEFINITION,))
    source = asyncio.run(registry.resolve(row))
    assert isinstance(source, CSVRowSource)
    assert source.materialization is SourceMaterialization.CAPTURED
    expected_id = f"csv:{quote(document_id, safe='')}:{quote(' 键%:/ ', safe='')}"
    assert source.source_id == source.name == expected_id
    restored = CSVRowSource.model_validate_json(source.model_dump_json())
    assert asyncio.run(registry.read(restored)) == row
    projection = registry.project(restored, TEXT_EVIDENCE_PROJECTION_KEY)
    expected_row = dict(zip(row.columns, row.values, strict=True))
    assert projection == {
        "source_type": "csv-row",
        "source_id": expected_id,
        "content": json.dumps(expected_row, ensure_ascii=False, separators=(",", ":")),
        "metadata": {
            "document_id": document_id,
            "primary_key": " id ",
            "primary_key_value": row.primary_key_value,
            "columns": list(row.columns),
            "row": expected_row,
        },
    }


@pytest.mark.parametrize(
    ("primary_key", "content"),
    [
        ("id", b"\n"),
        ("id", b'""\n'),
        ("", b"id,name\n"),
        ("id", b" id ,name\n"),
        ("id", b"id,name\n1,valid\n2,too,many\n"),
        ("id", b"id,name\n1,valid\n \t,blank\n"),
        ("id", b'id\n1\n""\n'),
        ("id", b'id,name\n1,valid\n2,"closed"tail\n'),
        ("id", b'id,name\n1,valid\n2,"unterminated'),
        ("id", b"id,name\n1,valid\n2,\xff"),
    ],
)
def test_invalid_documents_raise_even_after_valid_rows(primary_key: str, content: bytes) -> None:
    value = CSVDocumentInput(document_id="document", primary_key=primary_key, content=content)
    with pytest.raises(ValueError):
        parse_csv_document(value)


@pytest.mark.parametrize("document_id", ["", " ", "\tdoc", "doc\n"])
def test_header_only_documents_still_validate_document_identity(document_id: str) -> None:
    value = CSVDocumentInput(document_id=document_id, primary_key="id", content=b"id,name\n")
    with pytest.raises(ValueError):
        parse_csv_document(value)


def test_headers_and_keys_are_compared_exactly() -> None:
    rows = parse_csv_document(
        CSVDocumentInput(document_id="document", primary_key=" id ", content=b"id, id ,ID\n1, key ,x\n2,key,y\n")
    )
    assert [row.primary_key_value for row in rows] == [" key ", "key"]
    assert rows[0].columns == ("id", " id ", "ID")
    assert rows[0].values == ("1", " key ", "x")


def test_encoded_identity_length_limit_is_checked_before_returning_rows() -> None:
    assert len(csv_row_source_id("d", "x" * 250)) == 256
    assert len(csv_row_source_id("d", "界" * 27 + "x" * 7)) == 256
    for key in ("x" * 251, "界" * 28):
        with pytest.raises(ValueError):
            csv_row_source_id("d", key)
        value = CSVDocumentInput(document_id="d", primary_key="id", content=f"id\nvalid\n{key}\n".encode())
        with pytest.raises(ValueError):
            parse_csv_document(value)


@pytest.mark.parametrize(
    ("columns", "values", "primary_key_value"),
    [
        (("id", "name"), ("1",), "1"),
        (("id", "id"), ("1", "2"), "1"),
        (("id", " "), ("1", "value"), "1"),
        (("other", "name"), ("1", "value"), "1"),
        (("id", "name"), ("1", "value"), "different"),
        (("id", "name"), (" ", "value"), " "),
    ],
)
def test_direct_row_inputs_cannot_capture_inconsistent_records(
    columns: tuple[str, ...], values: tuple[str, ...], primary_key_value: str
) -> None:
    row = CSVRowInput(
        document_id="document",
        primary_key="id",
        primary_key_value=primary_key_value,
        columns=columns,
        values=values,
    )
    registry = SourceDefinitionRegistry((CSV_ROW_SOURCE_DEFINITION,))
    with pytest.raises(ValueError):
        asyncio.run(registry.resolve(row))
