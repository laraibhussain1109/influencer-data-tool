from influencer_service.rocketapi_insights import (
    DEFAULT_ROCKETAPI_TOKEN,
    fetch_rocketapi_insights_for_records,
)


class FakeRocketAPIClient:
    def get_web_profile_info(self, username):
        return {
            "response": {
                "body": {
                    "data": {
                        "user": {
                            "username": username,
                            "pk": "123",
                            "follower_count": 25000,
                            "female_percent": 58,
                            "male_percent": 42,
                            "age_18_24_percent": 21,
                            "age_25_34_percent": 49,
                            "age_35_45_percent": 20,
                            "age_45_plus_percent": 10,
                            "top_locations": [{"location": "Delhi", "percentage": 30}],
                        }
                    }
                }
            }
        }

    def get_user_media_by_username(self, username, *, count=12):
        return {
            "response": {
                "body": {
                    "items": [
                        {"id": "1", "media_type": 2, "play_count": 1000, "reach": 800, "like_count": 80, "comment_count": 8},
                        {"id": "2", "media_type": 2, "play_count": 3000, "reach": 1200, "like_count": 120, "comment_count": 12},
                    ]
                }
            }
        }

    def get_user_clips(self, user_id, *, count=12):
        return {"response": {"body": {"items": []}}}


def test_fetch_rocketapi_requires_token_without_client():
    payload = fetch_rocketapi_insights_for_records(
        [{"Instagram Link": "https://www.instagram.com/demo_user/"}],
        token=DEFAULT_ROCKETAPI_TOKEN,
    )

    assert payload["provider"]["name"] == "rocketapi"
    assert payload["provider"]["configured"] is False
    assert payload["complete_count"] == 0
    assert "RocketAPI token is not configured" in payload["results"][0]["error"]


def test_fetch_rocketapi_normalizes_profile_and_video_metrics():
    payload = fetch_rocketapi_insights_for_records(
        [{"Instagram Link": "https://www.instagram.com/demo_user/"}],
        token="test-token",
        client=FakeRocketAPIClient(),
    )

    assert payload["provider"]["configured"] is True
    assert payload["complete_count"] == 1
    insights = payload["results"][0]["insights"]
    assert insights["followers_summary"]["total"] == 25000
    assert insights["female_gender_ratio_percent"] == 58
    assert insights["avg_video_views_last_10"] == 2000
    assert insights["avg_video_reach_last_10"] == 1000
    assert insights["engagement_rate_per_reach_percent"] == 11
