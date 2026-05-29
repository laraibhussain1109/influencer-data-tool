import pytest

flask = pytest.importorskip("flask")

from influencer_service.app import create_app


def test_fetch_details_page_has_button():
    client = create_app().test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Calculate workbook details" in response.data
    assert b"Fetch public Instagram data" in response.data
    assert b"Workbook + public Instagram pages" in response.data
    assert b"/api/details" in response.data


def test_details_endpoint_combines_metrics_and_influencers():
    client = create_app().test_client()

    response = client.get("/api/details?city=Visakhapatnam&gender=Female")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data_source"]["mode"] == "workbook_plus_public_instagram"
    assert payload["data_source"]["instagram_public_fetch_enabled"] is True
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
