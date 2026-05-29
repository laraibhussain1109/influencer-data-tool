"""Provider-backed Instagram insight enrichment.

This module intentionally does not scrape Instagram. It reads insight data from a
configured provider API or JSON export so the app can return private metrics that
are not available from public Instagram pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request
import json
import os

from influencer_service.analytics import detect_columns
from influencer_service.instagram_public import username_from_instagram_url

REQUESTED_INSIGHT_FIELDS = (
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

FIELD_ALIASES = {
    "top_5_locations_percent": ("top_5_locations_percent", "top_locations", "audience_locations", "locations"),
    "female_gender_ratio_percent": ("female_gender_ratio_percent", "female_percent", "audience_female_percent"),
    "male_gender_ratio_percent": ("male_gender_ratio_percent", "male_percent", "audience_male_percent"),
    "18_24_age_ratio_percent": ("18_24_age_ratio_percent", "age_18_24_percent", "audience_18_24_percent"),
    "25_34_age_ratio_percent": ("25_34_age_ratio_percent", "age_25_34_percent", "audience_25_34_percent"),
    "35_45_age_ratio_percent": ("35_45_age_ratio_percent", "age_35_45_percent", "audience_35_45_percent"),
    "45_plus_age_ratio_percent": ("45_plus_age_ratio_percent", "age_45_plus_percent", "audience_45_plus_percent"),
    "engagement_rate_per_reach_percent": (
        "engagement_rate_per_reach_percent",
        "engagement_rate",
        "engagement_rate_percent",
    ),
    "followers_summary": ("followers_summary", "followers", "follower_count"),
    "avg_video_reach_last_10": ("avg_video_reach_last_10", "average_video_reach", "avg_reel_reach"),
    "avg_video_views_last_10": ("avg_video_views_last_10", "average_video_views", "avg_reel_views"),
}


@dataclass(frozen=True)
class ProviderConfig:
    api_url: str | None
    api_token: str | None
    file_path: Path | None

    @property
    def configured(self) -> bool:
        return bool(self.api_url or self.file_path)

    @property
    def mode(self) -> str:
        if self.api_url:
            return "http_api"
        if self.file_path:
            return "json_file"
        return "not_configured"


def fetch_insights_for_records(
    records: list[dict[str, Any]],
    *,
    provider_file: str | None = None,
) -> dict[str, Any]:
    """Fetch complete requested insight fields from a configured provider."""
    profiles = _profiles_from_records(records)
    config = _provider_config(provider_file)
    if not profiles:
        return _response(config, [], ["No Instagram link column or usernames were found in the workbook."])
    if not config.configured:
        return _response(
            config,
            [_missing_result(profile, "No insights provider is configured.") for profile in profiles],
            [
                "Set INSTAGRAM_INSIGHTS_PROVIDER_FILE to a JSON export, or set "
                "INSTAGRAM_INSIGHTS_API_URL/INSTAGRAM_INSIGHTS_API_TOKEN for a provider API."
            ],
        )

    try:
        raw_items = _load_file_items(config.file_path) if config.file_path else _fetch_api_items(config, profiles)
    except Exception as exc:
        return _response(config, [_missing_result(profile, str(exc)) for profile in profiles], [str(exc)])

    index = _index_items(raw_items)
    results = []
    for profile in profiles:
        item = index.get(profile["username"].casefold()) or index.get(profile["instagram_link"].casefold())
        if item is None:
            results.append(_missing_result(profile, "Provider did not return data for this profile."))
            continue
        insights = _normalize_insights(item)
        missing = [field for field, value in insights.items() if value is None or value == []]
        results.append(
            {
                "ok": not missing,
                "username": profile["username"],
                "instagram_link": profile["instagram_link"],
                "source": config.mode,
                "insights": insights,
                "missing_fields": missing,
                "error": None if not missing else "Provider response is missing one or more requested fields.",
            }
        )
    return _response(config, results, [result["error"] for result in results if result.get("error")])


def _provider_config(provider_file: str | None) -> ProviderConfig:
    file_value = provider_file or os.environ.get("INSTAGRAM_INSIGHTS_PROVIDER_FILE")
    return ProviderConfig(
        api_url=os.environ.get("INSTAGRAM_INSIGHTS_API_URL"),
        api_token=os.environ.get("INSTAGRAM_INSIGHTS_API_TOKEN"),
        file_path=Path(file_value).expanduser().resolve() if file_value else None,
    )


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


def _load_file_items(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    if not path.exists():
        raise FileNotFoundError(f"Insights provider file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if isinstance(data.get("profiles"), list):
            return data["profiles"]
        return [{"username": key, **value} for key, value in data.items() if isinstance(value, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    raise ValueError("Insights provider file must contain a JSON list, mapping, or {'profiles': [...]} object.")


def _fetch_api_items(config: ProviderConfig, profiles: list[dict[str, str]]) -> list[dict[str, Any]]:
    if not config.api_url:
        return []
    payload = json.dumps({"profiles": profiles, "fields": REQUESTED_INSIGHT_FIELDS}).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if config.api_token:
        headers["Authorization"] = f"Bearer {config.api_token}"
    req = request.Request(config.api_url, data=payload, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = json.loads(response.read().decode(response.headers.get_content_charset() or "utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError(f"Insights provider returned HTTP {exc.code}.") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach insights provider: {exc.reason}") from exc
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), list):
        return raw["profiles"]
    if isinstance(raw, list):
        return raw
    raise ValueError("Insights provider API must return a JSON list or {'profiles': [...]} object.")


def _index_items(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    index = {}
    for item in items:
        for key in ("username", "handle", "instagram_username", "instagram_link", "profile_url", "url"):
            value = item.get(key)
            if not value:
                continue
            username = username_from_instagram_url(value) or str(value).strip().strip("@")
            if username:
                index[username.casefold()] = item
            index[str(value).strip().casefold()] = item
    return index


def _normalize_insights(item: dict[str, Any]) -> dict[str, Any]:
    normalized = {field: _first_present(item, aliases) for field, aliases in FIELD_ALIASES.items()}
    followers = normalized["followers_summary"]
    if isinstance(followers, (int, float)):
        normalized["followers_summary"] = {
            "total": int(followers),
            "average": int(followers),
            "min": int(followers),
            "max": int(followers),
        }
    return normalized


def _first_present(item: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in item:
            return item[alias]
        nested = _nested_value(item, alias)
        if nested is not None:
            return nested
    return None


def _nested_value(item: dict[str, Any], alias: str) -> Any:
    for parent in ("insights", "metrics", "audience", "profile"):
        value = item.get(parent)
        if isinstance(value, dict) and alias in value:
            return value[alias]
    return None


def _missing_result(profile: dict[str, str], error_message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "username": profile["username"],
        "instagram_link": profile["instagram_link"],
        "source": "not_configured",
        "insights": {field: None for field in REQUESTED_INSIGHT_FIELDS},
        "missing_fields": list(REQUESTED_INSIGHT_FIELDS),
        "error": error_message,
    }


def _response(config: ProviderConfig, results: list[dict[str, Any]], errors: list[str | None]) -> dict[str, Any]:
    cleaned_errors = [error for error in errors if error]
    return {
        "provider": {
            "configured": config.configured,
            "mode": config.mode,
            "requested_fields": list(REQUESTED_INSIGHT_FIELDS),
        },
        "count": len(results),
        "complete_count": sum(1 for result in results if result.get("ok")),
        "results": results,
        "errors": cleaned_errors,
    }
