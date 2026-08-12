"""Workbook pipeline for Instagram deliverables."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from influencer_service.instagram import InstagramClient, collect_deliverable
from influencer_service.xlsx_reader import load_first_sheet

NAME_HEADERS = ("influencer_name", "full_name", "name")
URL_HEADERS = ("deliverable_url", "instagram_reel_url", "reel_url", "post_url", "instagram_link")


def collect_workbook(path: str | Path, client: InstagramClient) -> list[dict[str, Any]]:
    """Collect every deliverable in the first worksheet without aborting on row errors."""
    records = load_first_sheet(path)
    if not records:
        return []
    name_column = _find_header(records[0], NAME_HEADERS)
    url_column = _find_header(records[0], URL_HEADERS)
    if not url_column:
        raise ValueError(f"Workbook needs a deliverable URL column ({', '.join(URL_HEADERS)}).")

    results = []
    for row_number, row in enumerate(records, start=2):
        result: dict[str, Any] = {
            "row": row_number,
            "influencer_name": row.get(name_column) if name_column else None,
            "deliverable_url": row.get(url_column),
        }
        try:
            result.update(collect_deliverable(str(row.get(url_column) or ""), client))
            result["status"] = "partial" if result.get("warning") else "ok"
        except Exception as error:  # Keep a batch running when one deliverable is unavailable.
            result.update({"status": "error", "error": str(error)})
        results.append(result)
    return results


def write_results(path: str | Path, results: list[dict[str, Any]]) -> Path:
    """Write collection results to a new XLSX workbook."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Instagram Analytics"
    headers = [
        "Influencer Name", "Deliverable URL", "Status", "Likes", "Views", "Comments",
        "Comments Analyzed", "Comment Source", "Positive", "Neutral", "Negative", "Average Compound",
        "Warning", "Error", "Collected At (UTC)",
    ]
    sheet.append(headers)
    collected_at = datetime.now(timezone.utc).isoformat()
    for item in results:
        sentiment = item.get("sentiment", {})
        sheet.append([
            item.get("influencer_name"), item.get("deliverable_url"), item.get("status"),
            item.get("likes"), item.get("views"), item.get("comments"),
            item.get("comments_collected"), item.get("comments_source"), sentiment.get("positive"), sentiment.get("neutral"),
            sentiment.get("negative"), sentiment.get("average_compound"), item.get("warning"),
            item.get("error"),
            collected_at,
        ])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    workbook.save(output)
    return output


def _find_header(row: dict[str, Any], candidates: tuple[str, ...]) -> str | None:
    normalized = {str(key).strip().casefold().replace(" ", "_"): key for key in row}
    return next((normalized[name] for name in candidates if name in normalized), None)
