import pytest

flask = pytest.importorskip("flask")

from influencer_service.app import create_app


def test_fetch_details_page_has_button():
    client = create_app().test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Calculate workbook details" in response.data
    assert b"Fetch complete insights" in response.data
    assert b"Workbook + configured insights provider" in response.data
    assert b"/api/details" in response.data


def test_details_endpoint_combines_metrics_and_influencers():
    client = create_app().test_client()

    response = client.get("/api/details?city=Visakhapatnam&gender=Female")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data_source"]["mode"] == "workbook_plus_provider_insights"
    assert payload["data_source"]["provider_insights_enabled"] is True
    assert payload["data_source"]["instagram_private_insights_enabled"] is False
    assert payload["metrics"]["total_influencers"] == payload["influencer_count"]
    assert payload["influencer_count"] > 0
    assert all(item["city"] == "Visakhapatnam" for item in payload["influencers"])
    assert all(item["gender"] == "Female" for item in payload["influencers"])


def test_details_endpoint_can_fetch_public_instagram(monkeypatch):
    def fake_fetch(links):
        return [
            {
                "ok": True,
                "error": None,
                "profile": {
                    "username": "awantika.rai.35",
                    "followers": 17000,
                    "posts": 10,
                    "avg_video_views_last_10": 2500,
                    "videos_found": 2,
                },
            }
        ]

    monkeypatch.setattr("influencer_service.app.fetch_public_profiles", fake_fetch)
    client = create_app().test_client()

    response = client.get("/api/details?name=Awantika&include_public_instagram=1")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["public_instagram"]["count"] == 1
    assert payload["public_instagram"]["results"][0]["profile"]["followers"] == 17000


def test_details_endpoint_can_fetch_provider_insights(tmp_path):
    provider_file = tmp_path / "insights.json"
    provider_file.write_text(
        """{
          "profiles": [
            {
              "username": "awantika.rai.35",
              "top_5_locations_percent": [{"location": "Mumbai", "percentage": 42}],
              "female_gender_ratio_percent": 61,
              "male_gender_ratio_percent": 39,
              "18_24_age_ratio_percent": 20,
              "25_34_age_ratio_percent": 55,
              "35_45_age_ratio_percent": 20,
              "45_plus_age_ratio_percent": 5,
              "engagement_rate_per_reach_percent": 8.4,
              "followers": 17000,
              "avg_video_reach_last_10": 12000,
              "avg_video_views_last_10": 9800
            }
          ]
        }""",
        encoding="utf-8",
    )
    client = create_app().test_client()

    response = client.get(
        f"/api/details?name=Awantika&include_provider_insights=1&insights_file={provider_file}"
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["provider_insights"]["provider"]["mode"] == "json_file"
    assert payload["provider_insights"]["complete_count"] == 1
    insights = payload["provider_insights"]["results"][0]["insights"]
    assert insights["followers_summary"]["total"] == 17000
    assert insights["avg_video_views_last_10"] == 9800
