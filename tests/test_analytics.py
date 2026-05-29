from influencer_service.analytics import build_metrics, filter_records, normalize_records
from influencer_service.xlsx_reader import load_first_sheet


def test_load_default_workbook_and_compute_available_metrics():
    records = load_first_sheet("influencers.xlsx")

    assert len(records) > 0
    assert records[0]["Full Name"] == "Awantika Rai"

    metrics = build_metrics(records)

    assert metrics["total_influencers"] == len(records)
    assert metrics["female_gender_ratio_percent"] is not None
    assert metrics["followers"]["total"] > 0
    assert metrics["top_5_locations_percent"]
    assert "18_24_age_ratio_percent" in metrics["unavailable_fields"]
    assert "avg_video_views_last_10" in metrics["unavailable_fields"]


def test_filter_and_normalize_records():
    records = load_first_sheet("influencers.xlsx")
    filtered = filter_records(records, {"city": "Visakhapatnam", "gender": "Female"})
    normalized = normalize_records(filtered)

    assert filtered
    assert all(record["city"].lower() == "visakhapatnam" for record in normalized)
    assert all(record["gender"] == "Female" for record in normalized)
