from influencer_service.insights_provider import fetch_insights_for_records


def test_fetch_insights_for_records_reports_setup_when_no_provider(monkeypatch):
    monkeypatch.delenv("INSTAGRAM_INSIGHTS_PROVIDER_FILE", raising=False)
    monkeypatch.delenv("INSTAGRAM_INSIGHTS_API_URL", raising=False)

    payload = fetch_insights_for_records([
        {"Instagram Link": "https://www.instagram.com/demo_user/"}
    ])

    assert payload["provider"]["configured"] is False
    assert payload["count"] == 1
    assert payload["complete_count"] == 0
    assert "top_5_locations_percent" in payload["results"][0]["missing_fields"]


def test_fetch_insights_for_records_from_json_file(tmp_path):
    provider_file = tmp_path / "insights.json"
    provider_file.write_text(
        """{
          "demo_user": {
            "top_locations": [{"location": "Delhi", "percentage": 30}],
            "female_percent": 50,
            "male_percent": 50,
            "age_18_24_percent": 15,
            "age_25_34_percent": 45,
            "age_35_45_percent": 30,
            "age_45_plus_percent": 10,
            "engagement_rate": 7.5,
            "follower_count": 25000,
            "average_video_reach": 18000,
            "average_video_views": 16000
          }
        }""",
        encoding="utf-8",
    )

    payload = fetch_insights_for_records(
        [{"Instagram Link": "https://www.instagram.com/demo_user/"}],
        provider_file=str(provider_file),
    )

    assert payload["provider"]["configured"] is True
    assert payload["provider"]["mode"] == "json_file"
    assert payload["complete_count"] == 1
    insights = payload["results"][0]["insights"]
    assert insights["female_gender_ratio_percent"] == 50
    assert insights["followers_summary"]["total"] == 25000
    assert insights["avg_video_reach_last_10"] == 18000
