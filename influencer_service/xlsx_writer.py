"""Small XLSX updater for writing fetched influencer insights back to a workbook."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import re
import xml.etree.ElementTree as ET

from influencer_service.instagram_public import username_from_instagram_url
from influencer_service.xlsx_reader import MAIN_NS, NS, _column_index, _first_sheet_path, _read_rows, _read_shared_strings

ET.register_namespace("", MAIN_NS)

OUTPUT_COLUMNS = (
    "RocketAPI Username",
    "RocketAPI Fetch Status",
    "RocketAPI Missing Fields",
    "Top 5 locations (%)",
    "Female gender ratio (%)",
    "Male gender ratio (%)",
    "18-24 age ratio (%)",
    "25-34 age ratio (%)",
    "35-45 age ratio (%)",
    "45+ age ratio (%)",
    "Engagement rate per reach (%)",
    "Followers summary",
    "Avg. video reach (last 10 video average)",
    "Avg. video views (last 10 video average)",
)

FIELD_TO_COLUMN = {
    "top_5_locations_percent": "Top 5 locations (%)",
    "female_gender_ratio_percent": "Female gender ratio (%)",
    "male_gender_ratio_percent": "Male gender ratio (%)",
    "18_24_age_ratio_percent": "18-24 age ratio (%)",
    "25_34_age_ratio_percent": "25-34 age ratio (%)",
    "35_45_age_ratio_percent": "35-45 age ratio (%)",
    "45_plus_age_ratio_percent": "45+ age ratio (%)",
    "engagement_rate_per_reach_percent": "Engagement rate per reach (%)",
    "followers_summary": "Followers summary",
    "avg_video_reach_last_10": "Avg. video reach (last 10 video average)",
    "avg_video_views_last_10": "Avg. video views (last 10 video average)",
}


def update_workbook_with_insights(workbook_path: str | Path, provider_payload: dict[str, Any]) -> dict[str, Any]:
    """Write RocketAPI/provider insight results back to the first worksheet."""
    path = Path(workbook_path)
    if not path.exists():
        raise FileNotFoundError(f"Workbook not found: {path}")

    with ZipFile(path, "r") as archive:
        names = archive.namelist()
        shared_strings = _read_shared_strings(archive)
        sheet_path = _first_sheet_path(archive)
        rows = _read_rows(archive, sheet_path, shared_strings)
        sheet_root = ET.fromstring(archive.read(sheet_path))
        file_contents = {name: archive.read(name) for name in names if name != sheet_path}

    if not rows:
        raise ValueError("Workbook does not contain any rows to update.")

    headers = [_clean_header(value) for value in rows[0]]
    link_index = _instagram_link_index(headers)
    if link_index is None:
        raise ValueError("No Instagram link column was found in the workbook.")

    header_map = _ensure_headers(sheet_root, headers, OUTPUT_COLUMNS)
    result_map = _results_by_username(provider_payload)
    sheet_data = sheet_root.find("main:sheetData", NS)
    if sheet_data is None:
        raise ValueError("Worksheet does not contain sheetData.")

    updated_rows = 0
    unmatched_usernames: list[str] = []
    worksheet_rows = list(sheet_data.findall("main:row", NS))
    for row_number, values in enumerate(rows[1:], start=2):
        link = values[link_index] if link_index < len(values) else None
        username = username_from_instagram_url(link)
        if not username:
            continue
        result = result_map.get(username.casefold())
        if result is None:
            unmatched_usernames.append(username)
            continue
        row_el = _row_element(sheet_data, worksheet_rows, row_number)
        _write_result_to_row(row_el, header_map, result)
        updated_rows += 1

    _update_dimension(sheet_root, len(headers), len(rows))
    with NamedTemporaryFile("wb", delete=False, suffix=".xlsx", dir=path.parent) as tmp:
        temp_path = Path(tmp.name)
    try:
        with ZipFile(temp_path, "w", ZIP_DEFLATED) as archive:
            for name, content in file_contents.items():
                archive.writestr(name, content)
            archive.writestr(sheet_path, ET.tostring(sheet_root, encoding="utf-8", xml_declaration=True))
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    return {
        "workbook": str(path),
        "updated_rows": updated_rows,
        "unmatched_usernames": unmatched_usernames,
        "written_columns": list(OUTPUT_COLUMNS),
    }


def _write_result_to_row(row_el: ET.Element, header_map: dict[str, int], result: dict[str, Any]) -> None:
    insights = result.get("insights") or {}
    status = "Complete" if result.get("ok") else f"Incomplete: {result.get('error') or 'missing fields'}"
    values = {
        "RocketAPI Username": result.get("username"),
        "RocketAPI Fetch Status": status,
        "RocketAPI Missing Fields": ", ".join(result.get("missing_fields") or []),
    }
    for field, column in FIELD_TO_COLUMN.items():
        values[column] = _stringify(insights.get(field))
    for header, value in values.items():
        _set_cell(row_el, row_el.attrib["r"], header_map[header], value)


def _ensure_headers(sheet_root: ET.Element, headers: list[str], output_columns: tuple[str, ...]) -> dict[str, int]:
    sheet_data = sheet_root.find("main:sheetData", NS)
    if sheet_data is None:
        raise ValueError("Worksheet does not contain sheetData.")
    header_row = sheet_data.find("main:row", NS)
    if header_row is None:
        header_row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": "1"})
    header_map = {header: index + 1 for index, header in enumerate(headers) if header}
    for column in output_columns:
        if column not in header_map:
            headers.append(column)
            header_map[column] = len(headers)
            _set_cell(header_row, "1", header_map[column], column)
    return header_map


def _row_element(sheet_data: ET.Element, worksheet_rows: list[ET.Element], row_number: int) -> ET.Element:
    for row in worksheet_rows:
        if int(row.attrib.get("r", "0")) == row_number:
            return row
    row = ET.SubElement(sheet_data, f"{{{MAIN_NS}}}row", {"r": str(row_number)})
    worksheet_rows.append(row)
    return row


def _set_cell(row_el: ET.Element, row_number: str, column_index: int, value: Any) -> None:
    reference = f"{_column_letters(column_index)}{row_number}"
    cell = None
    for candidate in row_el.findall("main:c", NS):
        if candidate.attrib.get("r") == reference:
            cell = candidate
            break
    if cell is None:
        cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": reference})
        _insert_cell(row_el, cell, column_index)
    for child in list(cell):
        cell.remove(child)
    cell.attrib.pop("t", None)
    cell.attrib.pop("s", None)
    if value is None or value == "":
        return
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ET.SubElement(cell, f"{{{MAIN_NS}}}v").text = str(value)
        return
    cell.attrib["t"] = "inlineStr"
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    ET.SubElement(inline, f"{{{MAIN_NS}}}t").text = str(value)


def _insert_cell(row_el: ET.Element, cell: ET.Element, column_index: int) -> None:
    cells = list(row_el.findall("main:c", NS))
    for index, existing in enumerate(cells):
        existing_index = _column_index(existing.attrib.get("r", "A1"))
        if existing_index > column_index:
            row_el.insert(index, cell)
            return
    row_el.append(cell)


def _results_by_username(provider_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in provider_payload.get("results") or []:
        username = item.get("username")
        if username:
            result[str(username).casefold()] = item
    return result


def _instagram_link_index(headers: list[str]) -> int | None:
    for index, header in enumerate(headers):
        normalized = re.sub(r"[^a-z0-9]+", "_", header.casefold()).strip("_")
        if normalized in {"instagram_link", "instagram", "profile_link", "link"}:
            return index
    return None


def _update_dimension(sheet_root: ET.Element, column_count: int, row_count: int) -> None:
    dimension = sheet_root.find("main:dimension", NS)
    if dimension is not None:
        dimension.attrib["ref"] = f"A1:{_column_letters(column_count)}{row_count}"


def _stringify(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, dict):
        return "; ".join(f"{key}: {sub_value}" for key, sub_value in value.items())
    if isinstance(value, list):
        return "; ".join(_stringify(item) for item in value)
    return value


def _column_letters(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _clean_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())
