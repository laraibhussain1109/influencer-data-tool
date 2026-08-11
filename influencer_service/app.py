"""Flask app for serving Instagram influencer analytics from an XLSX file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

from influencer_service.analytics import build_metrics, filter_records, normalize_records
from influencer_service.deliverables import collect_workbook, write_results
from influencer_service.instagram import InstaloaderClient
from influencer_service.xlsx_reader import load_first_sheet

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKBOOK = REPO_ROOT / "influencers.xlsx"


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.errorhandler(FileNotFoundError)
    def workbook_not_found(error: FileNotFoundError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), 404

    @app.errorhandler(ValueError)
    def invalid_workbook(error: ValueError) -> tuple[Any, int]:
        return jsonify({"error": str(error)}), 400

    @app.get("/api/metrics")
    def metrics() -> Any:
        records, workbook = _load_records_from_request()
        payload = build_metrics(records)
        payload["source_file"] = str(workbook)
        return jsonify(payload)

    @app.get("/api/influencers")
    def influencers() -> Any:
        records, workbook = _load_records_from_request()
        filters = {
            key: value
            for key in ("name", "city", "state", "gender", "language")
            if (value := request.args.get(key))
        }
        filtered = filter_records(records, filters)
        return jsonify(
            {
                "source_file": str(workbook),
                "count": len(filtered),
                "results": normalize_records(filtered),
            }
        )

    @app.post("/api/deliverables/collect")
    def collect_deliverables() -> Any:
        """Collect an XLSX batch and write an enriched XLSX result file."""
        body = request.get_json(silent=True) or {}
        workbook = Path(body.get("file", DEFAULT_WORKBOOK)).expanduser().resolve()
        if not workbook.exists():
            raise FileNotFoundError(f"Workbook not found: {workbook}")
        try:
            max_comments = int(body.get("max_comments", 500))
        except (TypeError, ValueError) as error:
            raise ValueError("max_comments must be an integer.") from error
        if max_comments < 0:
            raise ValueError("max_comments must be zero or greater.")
        output = Path(body.get("output", REPO_ROOT / "instagram_analytics.xlsx")).expanduser().resolve()
        results = collect_workbook(workbook, InstaloaderClient(max_comments))
        write_results(output, results)
        return jsonify({
            "source_file": str(workbook),
            "output_file": str(output),
            "count": len(results),
            "succeeded": sum(item["status"] == "ok" for item in results),
            "failed": sum(item["status"] == "error" for item in results),
            "results": results,
        })

    return app


def _load_records_from_request() -> tuple[list[dict[str, Any]], Path]:
    workbook = Path(request.args.get("file", DEFAULT_WORKBOOK)).expanduser().resolve()
    if not workbook.exists():
        raise FileNotFoundError(f"Workbook not found: {workbook}")
    return load_first_sheet(workbook), workbook


app = create_app()
