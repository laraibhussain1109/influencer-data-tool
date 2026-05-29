"""Small XLSX reader for simple tabular workbooks.

The service only needs the first worksheet from the local influencer workbook, so this
module intentionally avoids a heavyweight runtime dependency such as pandas.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import ZipFile
import re
import xml.etree.ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"main": MAIN_NS, "rel": REL_NS, "pkg": PACKAGE_REL_NS}


def load_first_sheet(path: str | Path) -> list[dict[str, Any]]:
    """Read the first worksheet from an XLSX file into a list of dictionaries."""
    workbook_path = Path(path)
    with ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        rows = _read_rows(archive, sheet_path, shared_strings)

    if not rows:
        return []

    headers = [_clean_header(value) for value in rows[0]]
    records: list[dict[str, Any]] = []
    for row in rows[1:]:
        record: dict[str, Any] = {}
        has_value = False
        for index, header in enumerate(headers):
            if not header:
                continue
            value = row[index] if index < len(row) else None
            if value not in (None, ""):
                has_value = True
            record[header] = value
        if has_value:
            records.append(record)
    return records


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("main:si", NS):
        texts = [node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t")]
        strings.append("".join(texts))
    return strings


def _first_sheet_path(archive: ZipFile) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    first_sheet = workbook.find("main:sheets/main:sheet", NS)
    if first_sheet is None:
        raise ValueError("Workbook does not contain any worksheets.")

    relationship_id = first_sheet.attrib[f"{{{REL_NS}}}id"]
    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall("pkg:Relationship", NS):
        if rel.attrib.get("Id") == relationship_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError("Could not resolve the first worksheet path.")


def _read_rows(archive: ZipFile, sheet_path: str, shared_strings: list[str]) -> list[list[Any]]:
    root = ET.fromstring(archive.read(sheet_path))
    parsed_rows: list[list[Any]] = []
    for row in root.findall("main:sheetData/main:row", NS):
        values: list[Any] = []
        for cell in row.findall("main:c", NS):
            column_index = _column_index(cell.attrib.get("r", "A1"))
            while len(values) < column_index:
                values.append(None)
            values.append(_cell_value(cell, shared_strings))
        parsed_rows.append(values)
    return parsed_rows


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))

    value_node = cell.find("main:v", NS)
    if value_node is None or value_node.text is None:
        return None

    raw_value = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw_value)]
    if cell_type == "b":
        return raw_value == "1"
    if cell_type == "str":
        return raw_value
    return _coerce_number(raw_value)


def _column_index(reference: str) -> int:
    letters = re.sub(r"[^A-Z]", "", reference.upper())
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index


def _coerce_number(value: str) -> int | float | str:
    try:
        number = float(value)
    except ValueError:
        return value
    if number.is_integer():
        return int(number)
    return number


def _clean_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
