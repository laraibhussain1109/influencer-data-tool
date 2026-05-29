import pytest

flask = pytest.importorskip("flask")

from influencer_service.app import create_app


def test_fetch_details_page_has_button():
    client = create_app().test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Calculate workbook details" in response.data
    assert b"No live Instagram API or scraper is configured" in response.data
    assert b"/api/details" in response.data


def test_details_endpoint_combines_metrics_and_influencers():
    client = create_app().test_client()

    response = client.get("/api/details?city=Visakhapatnam&gender=Female")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["data_source"]["mode"] == "workbook_only"
    assert payload["data_source"]["instagram_api_enabled"] is False
    assert payload["metrics"]["total_influencers"] == payload["influencer_count"]
    assert payload["influencer_count"] > 0
    assert all(item["city"] == "Visakhapatnam" for item in payload["influencers"])
    assert all(item["gender"] == "Female" for item in payload["influencers"])
