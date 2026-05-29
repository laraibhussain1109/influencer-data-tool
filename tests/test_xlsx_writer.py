from pathlib import Path
from zipfile import ZipFile
import shutil

from influencer_service.xlsx_reader import load_first_sheet
from influencer_service.xlsx_writer import update_workbook_with_insights


def test_update_workbook_with_insights_writes_requested_columns(tmp_path):
    workbook = tmp_path / "influencers.xlsx"
    shutil.copyfile("influencers.xlsx", workbook)
    payload = {
        "results": [
            {
                "ok": True,
                "username": "awantika.rai.35",
                "insights": {
                    "top_5_locations_percent": [{"location": "Mumbai", "percentage": 42}],
                    "female_gender_ratio_percent": 61,
                    "male_gender_ratio_percent": 39,
                    "18_24_age_ratio_percent": 20,
                    "25_34_age_ratio_percent": 55,
                    "35_45_age_ratio_percent": 20,
                    "45_plus_age_ratio_percent": 5,
                    "engagement_rate_per_reach_percent": 8.4,
                    "followers_summary": {"total": 17000, "average": 17000, "min": 17000, "max": 17000},
                    "avg_video_reach_last_10": 12000,
                    "avg_video_views_last_10": 9800,
                },
                "missing_fields": [],
                "error": None,
            }
        ]
    }

    result = update_workbook_with_insights(workbook, payload)
    records = load_first_sheet(workbook)
    row = records[0]

    assert result["updated_rows"] == 1
    assert row["RocketAPI Username"] == "awantika.rai.35"
    assert row["RocketAPI Fetch Status"] == "Complete"
    assert row["Female gender ratio (%)"] == 61
    assert row["Avg. video views (last 10 video average)"] == 9800
    assert "Mumbai" in row["Top 5 locations (%)"]

    with ZipFile(workbook) as archive:
        assert archive.testzip() is None
