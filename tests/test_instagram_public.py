import json

from influencer_service.instagram_public import parse_public_profile_html, username_from_instagram_url


def test_username_from_instagram_url():
    assert username_from_instagram_url("https://www.instagram.com/example.creator?igsh=abc") == "example.creator"
    assert username_from_instagram_url("@demo_user") == "demo_user"
    assert username_from_instagram_url("https://www.instagram.com/p/shortcode") is None


def test_parse_public_profile_html_extracts_counts_and_video_average():
    payload = {
        "graphql": {
            "user": {
                "username": "demo_user",
                "full_name": "Demo User",
                "biography": "Public bio",
                "is_private": False,
                "is_verified": True,
                "edge_followed_by": {"count": 12345},
                "edge_follow": {"count": 321},
                "edge_owner_to_timeline_media": {
                    "count": 2,
                    "edges": [
                        {"node": {"is_video": True, "shortcode": "a", "video_view_count": 1000, "edge_liked_by": {"count": 100}, "edge_media_to_comment": {"count": 10}}},
                        {"node": {"is_video": True, "shortcode": "b", "video_view_count": 3000, "edge_liked_by": {"count": 300}, "edge_media_to_comment": {"count": 30}}},
                        {"node": {"is_video": False, "shortcode": "c"}},
                    ],
                },
            }
        }
    }
    html = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script>'

    profile = parse_public_profile_html(html, username="demo_user", profile_url="https://www.instagram.com/demo_user/")

    assert profile.followers == 12345
    assert profile.following == 321
    assert profile.posts == 2
    assert profile.full_name == "Demo User"
    assert profile.avg_video_views_last_10 == 2000
    assert profile.avg_video_likes_last_10 == 200
    assert profile.avg_video_comments_last_10 == 20
    assert profile.videos_found == 2
