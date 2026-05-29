"""Fetch public Instagram profile data for workbook rows.

The fetcher uses Instagram's public profile page metadata only. It does not log in,
use private APIs, bypass access controls, or fetch private audience insights.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from html import unescape
from typing import Any
from urllib import error, request
import json
import re
import time

INSTAGRAM_PROFILE_URL = "https://www.instagram.com/{username}/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
VIEW_COUNT_KEYS = ("video_view_count", "play_count", "ig_play_count", "view_count")
LIKE_COUNT_KEYS = ("edge_liked_by", "like_count")
COMMENT_COUNT_KEYS = ("edge_media_to_comment", "comment_count")


@dataclass(frozen=True)
class InstagramPublicProfile:
    username: str
    profile_url: str
    followers: int | None
    following: int | None
    posts: int | None
    full_name: str | None
    biography: str | None
    is_private: bool | None
    is_verified: bool | None
    avg_video_views_last_10: float | None
    avg_video_likes_last_10: float | None
    avg_video_comments_last_10: float | None
    videos_found: int
    source: str = "instagram_public_page"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def fetch_public_profiles(
    instagram_links: list[str],
    *,
    delay_seconds: float = 1.0,
    timeout_seconds: float = 12.0,
) -> list[dict[str, Any]]:
    """Fetch public profile metadata for all unique Instagram links."""
    results = []
    seen_usernames: set[str] = set()
    for link in instagram_links:
        username = username_from_instagram_url(link)
        if not username or username in seen_usernames:
            continue
        seen_usernames.add(username)
        result = fetch_public_profile(username, timeout_seconds=timeout_seconds)
        results.append(result)
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return results


def fetch_public_profile(username: str, *, timeout_seconds: float = 12.0) -> dict[str, Any]:
    """Fetch one public Instagram profile page and parse public metadata."""
    profile_url = INSTAGRAM_PROFILE_URL.format(username=username)
    try:
        html = _download_profile_html(profile_url, timeout_seconds=timeout_seconds)
        profile = parse_public_profile_html(html, username=username, profile_url=profile_url)
        return {"ok": True, "error": None, "profile": profile.to_dict()}
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "profile": InstagramPublicProfile(
                username=username,
                profile_url=profile_url,
                followers=None,
                following=None,
                posts=None,
                full_name=None,
                biography=None,
                is_private=None,
                is_verified=None,
                avg_video_views_last_10=None,
                avg_video_likes_last_10=None,
                avg_video_comments_last_10=None,
                videos_found=0,
            ).to_dict(),
        }


def parse_public_profile_html(html: str, *, username: str, profile_url: str) -> InstagramPublicProfile:
    """Parse public profile metadata embedded in an Instagram profile page."""
    data = _extract_json_data(html)
    user = _find_user_data(data, username) if data is not None else {}
    videos = _find_recent_videos(user)
    last_10_videos = videos[:10]

    return InstagramPublicProfile(
        username=username,
        profile_url=profile_url,
        followers=_first_int(user, "edge_followed_by.count", "followers", "follower_count")
        or _interaction_count(user, "follow"),
        following=_first_int(user, "edge_follow.count", "following", "following_count"),
        posts=_first_int(user, "edge_owner_to_timeline_media.count", "media_count", "posts")
        or _interaction_count(user, "write"),
        full_name=_first_str(user, "full_name", "name"),
        biography=_first_str(user, "biography", "bio"),
        is_private=_first_bool(user, "is_private"),
        is_verified=_first_bool(user, "is_verified"),
        avg_video_views_last_10=_average(_first_int(video, *VIEW_COUNT_KEYS) for video in last_10_videos),
        avg_video_likes_last_10=_average(_first_int(video, *LIKE_COUNT_KEYS) for video in last_10_videos),
        avg_video_comments_last_10=_average(_first_int(video, *COMMENT_COUNT_KEYS) for video in last_10_videos),
        videos_found=len(videos),
    )


def username_from_instagram_url(value: Any) -> str | None:
    """Extract an Instagram username from a link or plain handle."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.split("?", 1)[0].strip().rstrip("/")
    if "/" not in text and not text.startswith("@"):
        return _clean_username(text)
    match = re.search(r"(?:https?://)?(?:www\.)?instagram\.com/([^/?#]+)", text, re.IGNORECASE)
    if not match:
        return _clean_username(text.lstrip("@"))
    username = match.group(1)
    if username in {"p", "reel", "tv", "stories", "explore"}:
        return None
    return _clean_username(username)


def _download_profile_html(profile_url: str, *, timeout_seconds: float) -> str:
    req = request.Request(
        profile_url,
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except error.HTTPError as exc:
        raise RuntimeError(f"Instagram returned HTTP {exc.code} for {profile_url}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Could not reach Instagram for {profile_url}: {exc.reason}") from exc


def _extract_json_data(html: str) -> Any:
    for pattern in (
        r'<script type="application/ld\+json">(.*?)</script>',
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        r"window\._sharedData\s*=\s*(\{.*?\});</script>",
    ):
        match = re.search(pattern, html, re.DOTALL)
        if match:
            return json.loads(unescape(match.group(1)))
    raise ValueError("No public Instagram profile metadata was found in the page HTML.")


def _find_user_data(data: Any, username: str) -> dict[str, Any]:
    if isinstance(data, dict):
        if _looks_like_user(data, username):
            return data
        graphql_user = data.get("graphql", {}).get("user")
        if isinstance(graphql_user, dict):
            return graphql_user
        for key in ("user", "owner", "profilePage", "mainEntity"):
            nested = data.get(key)
            if isinstance(nested, dict):
                found = _find_user_data(nested, username)
                if found:
                    return found
        for value in data.values():
            found = _find_user_data(value, username)
            if found:
                return found
    elif isinstance(data, list):
        for value in data:
            found = _find_user_data(value, username)
            if found:
                return found
    return {}


def _looks_like_user(data: dict[str, Any], username: str) -> bool:
    username_values = [data.get("username"), data.get("alternateName"), data.get("identifier")]
    normalized = {str(value).strip("@").casefold() for value in username_values if value}
    has_counts = any(key in data for key in ("edge_followed_by", "followers", "follower_count"))
    return username.casefold() in normalized or has_counts


def _find_recent_videos(user: dict[str, Any]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    media = user.get("edge_owner_to_timeline_media", {}).get("edges", [])
    if isinstance(media, list):
        for edge in media:
            node = edge.get("node") if isinstance(edge, dict) else None
            if isinstance(node, dict) and _is_video(node):
                videos.append(node)
    if not videos:
        videos.extend(_collect_video_nodes(user))
    return videos


def _collect_video_nodes(value: Any) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    if isinstance(value, dict):
        if _is_video(value):
            videos.append(value)
        for nested in value.values():
            videos.extend(_collect_video_nodes(nested))
    elif isinstance(value, list):
        for nested in value:
            videos.extend(_collect_video_nodes(nested))
    deduped = []
    seen = set()
    for video in videos:
        shortcode = video.get("shortcode") or video.get("code") or id(video)
        if shortcode not in seen:
            seen.add(shortcode)
            deduped.append(video)
    return deduped


def _is_video(value: dict[str, Any]) -> bool:
    return bool(value.get("is_video")) or value.get("__typename") in {"GraphVideo", "XDTGraphVideo"}


def _interaction_count(data: dict[str, Any], interaction_name: str) -> int | None:
    stats = data.get("interactionStatistic") or data.get("interaction_statistic")
    if isinstance(stats, dict):
        stats = [stats]
    if not isinstance(stats, list):
        return None
    for stat in stats:
        if not isinstance(stat, dict):
            continue
        interaction_type = str(stat.get("interactionType", "")).casefold()
        if interaction_name not in interaction_type:
            continue
        value = stat.get("userInteractionCount") or stat.get("count")
        if value is None:
            continue
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            continue
    return None


def _first_str(data: dict[str, Any], *paths: str) -> str | None:
    for path in paths:
        value = _path_value(data, path)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_bool(data: dict[str, Any], *paths: str) -> bool | None:
    for path in paths:
        value = _path_value(data, path)
        if isinstance(value, bool):
            return value
    return None


def _first_int(data: dict[str, Any], *paths: str) -> int | None:
    for path in paths:
        value = _path_value(data, path)
        if isinstance(value, dict) and "count" in value:
            value = value["count"]
        if isinstance(value, bool) or value is None:
            continue
        try:
            return int(float(str(value).replace(",", "")))
        except ValueError:
            continue
    return None


def _path_value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _average(values: Any) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 2)


def _clean_username(value: str) -> str | None:
    username = value.strip().strip("@").strip("/")
    return username if re.fullmatch(r"[A-Za-z0-9._]{1,30}", username) else None
