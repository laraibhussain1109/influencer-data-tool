"""RocketAPI-backed Instagram data fetching for workbook links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from urllib import error, request
import json
import math
import os

from influencer_service.analytics import detect_columns
from influencer_service.instagram_public import username_from_instagram_url

ROCKETAPI_BASE_URL = "https://v1.rocketapi.io"
DEFAULT_ROCKETAPI_TOKEN = "ROCKETAPI_API_KEY_REPLACE_ME"
REQUESTED_FIELDS = (
    "top_5_locations_percent",
    "female_gender_ratio_percent",
    "male_gender_ratio_percent",
    "18_24_age_ratio_percent",
    "25_34_age_ratio_percent",
    "35_45_age_ratio_percent",
    "45_plus_age_ratio_percent",
    "engagement_rate_per_reach_percent",
    "followers_summary",
    "avg_video_reach_last_10",
    "avg_video_views_last_10",
)
AUDIENCE_LOCATION_KEYS = (
    "top_5_locations_percent",
    "top_locations",
    "audience_locations",
    "audience_city",
    "audience_cities",
    "follower_demographics_city",
)
FEMALE_KEYS = ("female_gender_ratio_percent", "female_percent", "audience_female_percent", "follower_gender_female")
MALE_KEYS = ("male_gender_ratio_percent", "male_percent", "audience_male_percent", "follower_gender_male")
AGE_KEYS = {
    "18_24_age_ratio_percent": ("18_24_age_ratio_percent", "age_18_24_percent", "audience_18_24_percent", "age_18_24"),
    "25_34_age_ratio_percent": ("25_34_age_ratio_percent", "age_25_34_percent", "audience_25_34_percent", "age_25_34"),
    "35_45_age_ratio_percent": ("35_45_age_ratio_percent", "age_35_45_percent", "audience_35_45_percent", "age_35_45"),
    "45_plus_age_ratio_percent": ("45_plus_age_ratio_percent", "age_45_plus_percent", "audience_45_plus_percent", "age_45_plus"),
}
FOLLOWER_KEYS = ("follower_count", "followers", "edge_followed_by.count")
VIEW_KEYS = ("play_count", "ig_play_count", "video_view_count", "view_count", "views")
REACH_KEYS = ("reach", "organic_reach", "video_reach", "ig_reach")
LIKE_KEYS = ("like_count", "like_and_view_counts_disabled", "edge_liked_by.count")
COMMENT_KEYS = ("comment_count", "edge_media_to_comment.count")
SAVE_KEYS = ("save_count", "saved_count")
SHARE_KEYS = ("share_count", "reshare_count")


@dataclass(frozen=True)
class RocketAPIConfig:
    token: str
    base_url: str = ROCKETAPI_BASE_URL

    @property
    def configured(self) -> bool:
        return bool(self.token and self.token != DEFAULT_ROCKETAPI_TOKEN)


class RocketAPIClient:
    """Small HTTP client for the RocketAPI endpoints used by this service."""

    def __init__(self, token: str, *, base_url: str = ROCKETAPI_BASE_URL, timeout_seconds: float = 60.0) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_web_profile_info(self, username: str) -> dict[str, Any]:
        return self._post("/instagram/user/get_web_profile_info", {"username": username})

    def get_user_media_by_username(self, username: str, *, count: int = 12) -> dict[str, Any]:
        return self._post("/instagram/user/get_media_by_username", {"username": username, "count": count})

    def get_user_clips(self, user_id: int | str, *, count: int = 12) -> dict[str, Any]:
        return self._post("/instagram/user/get_clips", {"id": user_id, "count": count})

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        req = request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Token {self.token}"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode(response.headers.get_content_charset() or "utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"RocketAPI returned HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Could not reach RocketAPI: {exc.reason}") from exc


def fetch_rocketapi_insights_for_records(
    records: list[dict[str, Any]],
    *,
    token: str | None = None,
    client: RocketAPIClient | None = None,
) -> dict[str, Any]:
    """Fetch all available requested Instagram details from RocketAPI."""
    profiles = _profiles_from_records(records)
    config = RocketAPIConfig(token=(token or os.environ.get("ROCKETAPI_TOKEN") or DEFAULT_ROCKETAPI_TOKEN).strip())
    if not profiles:
        return _response(config, [], ["No Instagram link column or usernames were found in the workbook."])
    if client is None and not config.configured:
        return _response(
            config,
            [_missing_result(profile, "RocketAPI token is not configured.") for profile in profiles],
            ["Replace ROCKETAPI_API_KEY_REPLACE_ME with your RocketAPI key or set ROCKETAPI_TOKEN."],
        )

    api = client or RocketAPIClient(config.token, base_url=config.base_url)
    results = []
    for profile in profiles:
        try:
            profile_payload = api.get_web_profile_info(profile["username"])
            media_payload = api.get_user_media_by_username(profile["username"], count=12)
            user = _first_user(profile_payload) or {}
            user_id = _first_value(user, ("pk", "pk_id", "id"))
            clips_payload = api.get_user_clips(user_id, count=12) if user_id else {}
            insights = _build_insights(user, media_payload, clips_payload, profile_payload)
            missing = [field for field in REQUESTED_FIELDS if _missing(insights.get(field))]
            results.append(
                {
                    "ok": not missing,
                    "username": profile["username"],
                    "instagram_link": profile["instagram_link"],
                    "source": "rocketapi",
                    "insights": insights,
                    "missing_fields": missing,
                    "error": None if not missing else "RocketAPI response did not include one or more requested fields.",
                }
            )
        except Exception as exc:
            results.append(_missing_result(profile, str(exc)))
    return _response(config, results, [result["error"] for result in results if result.get("error")])


def _profiles_from_records(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    columns = detect_columns(records)
    if not columns.instagram_link:
        return []
    profiles = []
    seen = set()
    for row in records:
        link = str(row.get(columns.instagram_link, "")).strip()
        username = username_from_instagram_url(link)
        if not username or username.casefold() in seen:
            continue
        seen.add(username.casefold())
        profiles.append({"username": username, "instagram_link": link})
    return profiles


def _build_insights(
    user: dict[str, Any],
    media_payload: dict[str, Any],
    clips_payload: dict[str, Any],
    profile_payload: dict[str, Any],
) -> dict[str, Any]:
    media_items = _items_from_payload(media_payload)
    clip_items = _items_from_payload(clips_payload)
    videos = _video_items([*clip_items, *media_items])[:10]
    followers = _first_number(user, FOLLOWER_KEYS) or _first_number(profile_payload, FOLLOWER_KEYS)
    total_reach = sum(value for value in (_first_number(item, REACH_KEYS) for item in videos) if value is not None)
    total_engagement = sum(_engagement_count(item) for item in videos)
    return {
        "top_5_locations_percent": _top_locations(profile_payload) or _top_locations(user),
        "female_gender_ratio_percent": _first_percent(profile_payload, FEMALE_KEYS) or _first_percent(user, FEMALE_KEYS),
        "male_gender_ratio_percent": _first_percent(profile_payload, MALE_KEYS) or _first_percent(user, MALE_KEYS),
        "18_24_age_ratio_percent": _age_percent(profile_payload, user, "18_24_age_ratio_percent"),
        "25_34_age_ratio_percent": _age_percent(profile_payload, user, "25_34_age_ratio_percent"),
        "35_45_age_ratio_percent": _age_percent(profile_payload, user, "35_45_age_ratio_percent"),
        "45_plus_age_ratio_percent": _age_percent(profile_payload, user, "45_plus_age_ratio_percent"),
        "engagement_rate_per_reach_percent": round((total_engagement / total_reach) * 100, 2) if total_reach else None,
        "followers_summary": _followers_summary(followers),
        "avg_video_reach_last_10": _average(_first_number(item, REACH_KEYS) for item in videos),
        "avg_video_views_last_10": _average(_first_number(item, VIEW_KEYS) for item in videos),
    }


def _first_user(payload: dict[str, Any]) -> dict[str, Any] | None:
    for candidate in _walk_dicts(payload):
        if any(key in candidate for key in ("username", "follower_count", "edge_followed_by")):
            return candidate
    return None


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for candidate in _walk_dicts(payload):
        items = candidate.get("items") or candidate.get("media") or candidate.get("clips")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return []


def _video_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    videos = []
    seen = set()
    for item in items:
        if not _is_video(item):
            continue
        item_id = str(_first_value(item, ("id", "pk", "code", "shortcode")) or id(item))
        if item_id in seen:
            continue
        seen.add(item_id)
        videos.append(item)
    return videos


def _is_video(item: dict[str, Any]) -> bool:
    media_type = _first_value(item, ("media_type", "product_type", "media_product_type", "__typename"))
    if isinstance(media_type, str):
        return media_type.casefold() in {"video", "clips", "reels", "igtv", "graphvideo", "xdtgraphvideo"}
    return media_type == 2 or bool(item.get("is_video")) or any(_first_number(item, (key,)) is not None for key in VIEW_KEYS)


def _top_locations(*payloads: dict[str, Any]) -> list[dict[str, Any]] | None:
    for payload in payloads:
        value = _first_value(payload, AUDIENCE_LOCATION_KEYS)
        if isinstance(value, list):
            return value[:5]
        if isinstance(value, dict):
            rows = []
            for location, percentage in value.items():
                rows.append({"location": location, "percentage": _to_percent(percentage)})
            return rows[:5]
    return None


def _age_percent(profile_payload: dict[str, Any], user: dict[str, Any], field: str) -> float | None:
    return _first_percent(profile_payload, AGE_KEYS[field]) or _first_percent(user, AGE_KEYS[field])


def _followers_summary(followers: float | None) -> dict[str, Any] | None:
    if followers is None:
        return None
    value = int(followers)
    return {"total": value, "average": value, "min": value, "max": value}


def _engagement_count(item: dict[str, Any]) -> float:
    return sum(_first_number(item, keys) or 0 for keys in (LIKE_KEYS, COMMENT_KEYS, SAVE_KEYS, SHARE_KEYS))


def _first_percent(payload: dict[str, Any], keys: Iterable[str]) -> float | None:
    value = _first_value(payload, keys)
    return _to_percent(value)


def _first_number(payload: dict[str, Any], keys: Iterable[str]) -> float | None:
    for key in keys:
        value = _first_value(payload, (key,))
        if isinstance(value, dict) and "count" in value:
            value = value["count"]
        if isinstance(value, bool) or value is None:
            continue
        try:
            number = float(str(value).replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(number):
            return number
    return None


def _to_percent(value: Any) -> float | None:
    number = _first_number({"value": value}, ("value",))
    if number is None:
        return None
    return round(number * 100 if 0 <= number <= 1 else number, 2)


def _first_value(payload: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = _path_value(payload, key)
        if value is not None:
            return value
        normalized_key = key.replace(".", "_").casefold()
        for candidate in _walk_dicts(payload):
            for candidate_key, candidate_value in candidate.items():
                if str(candidate_key).casefold() == normalized_key or str(candidate_key).casefold() == key.casefold():
                    return candidate_value
    return None


def _path_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _walk_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_dicts(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_dicts(nested)


def _average(values: Iterable[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    return round(sum(numbers) / len(numbers), 2) if numbers else None


def _missing(value: Any) -> bool:
    return value is None or value == [] or value == {}


def _missing_result(profile: dict[str, str], error_message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "username": profile["username"],
        "instagram_link": profile["instagram_link"],
        "source": "rocketapi",
        "insights": {field: None for field in REQUESTED_FIELDS},
        "missing_fields": list(REQUESTED_FIELDS),
        "error": error_message,
    }


def _response(config: RocketAPIConfig, results: list[dict[str, Any]], errors: list[str | None]) -> dict[str, Any]:
    return {
        "provider": {
            "name": "rocketapi",
            "configured": config.configured,
            "base_url": config.base_url,
            "requested_fields": list(REQUESTED_FIELDS),
        },
        "count": len(results),
        "complete_count": sum(1 for result in results if result.get("ok")),
        "results": results,
        "errors": [error for error in errors if error],
    }
