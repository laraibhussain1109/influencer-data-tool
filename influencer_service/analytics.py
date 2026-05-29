"""Analytics helpers for influencer workbook records."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable
import math
import re

AGE_BUCKETS = ("18-24", "25-34", "35-45", "45+")
MISSING_METRICS = {
    "18_24_age_ratio_percent": "No age, age group, or 18-24 audience-ratio column was found.",
    "25_34_age_ratio_percent": "No age, age group, or 25-34 audience-ratio column was found.",
    "35_45_age_ratio_percent": "No age, age group, or 35-45 audience-ratio column was found.",
    "45_plus_age_ratio_percent": "No age, age group, or 45+ audience-ratio column was found.",
    "engagement_rate_per_reach_percent": "No engagement/reach columns were found.",
    "avg_video_reach_last_10": "No video reach columns were found.",
    "avg_video_views_last_10": "No video view columns were found.",
}


@dataclass(frozen=True)
class ColumnMap:
    full_name: str | None
    instagram_link: str | None
    followers: str | None
    gender: str | None
    city: str | None
    state: str | None
    language: str | None
    age: str | None
    age_group: str | None
    reach: str | None
    engagement: str | None
    likes: str | None
    comments: str | None
    shares: str | None
    saves: str | None
    video_reach: tuple[str, ...]
    video_views: tuple[str, ...]
    age_ratio_columns: dict[str, str]


def build_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate influencer metrics for API responses."""
    columns = detect_columns(records)
    followers = [_to_number(row.get(columns.followers)) for row in records] if columns.followers else []
    followers = [value for value in followers if value is not None]

    metrics: dict[str, Any] = {
        "total_influencers": len(records),
        "top_5_locations_percent": _top_locations(records, columns),
        "female_gender_ratio_percent": _gender_ratio(records, columns, "female"),
        "male_gender_ratio_percent": _gender_ratio(records, columns, "male"),
        "18_24_age_ratio_percent": _age_ratio(records, columns, "18-24"),
        "25_34_age_ratio_percent": _age_ratio(records, columns, "25-34"),
        "35_45_age_ratio_percent": _age_ratio(records, columns, "35-45"),
        "45_plus_age_ratio_percent": _age_ratio(records, columns, "45+"),
        "engagement_rate_per_reach_percent": _engagement_rate(records, columns),
        "followers": _followers_summary(followers),
        "avg_video_reach_last_10": _last_10_average(records, columns.video_reach),
        "avg_video_views_last_10": _last_10_average(records, columns.video_views),
    }
    metrics["available_columns"] = list(records[0].keys()) if records else []
    metrics["unavailable_fields"] = {
        key: reason for key, reason in MISSING_METRICS.items() if metrics.get(key) is None
    }
    return metrics


def normalize_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return API-friendly records with known fields normalized and original fields preserved."""
    columns = detect_columns(records)
    normalized = []
    for index, row in enumerate(records, start=1):
        normalized.append(
            {
                "id": index,
                "full_name": row.get(columns.full_name) if columns.full_name else None,
                "instagram_link": row.get(columns.instagram_link) if columns.instagram_link else None,
                "followers": _to_number(row.get(columns.followers)) if columns.followers else None,
                "gender": row.get(columns.gender) if columns.gender else None,
                "city": row.get(columns.city) if columns.city else None,
                "state": row.get(columns.state) if columns.state else None,
                "language": row.get(columns.language) if columns.language else None,
                "raw": row,
            }
        )
    return normalized


def filter_records(records: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    """Filter records by common query parameters."""
    if not filters:
        return records
    columns = detect_columns(records)
    filter_to_column = {
        "name": columns.full_name,
        "city": columns.city,
        "state": columns.state,
        "gender": columns.gender,
        "language": columns.language,
    }
    filtered = records
    for key, expected in filters.items():
        column = filter_to_column.get(key)
        if not column or not expected:
            continue
        expected_norm = expected.strip().casefold()
        filtered = [
            row
            for row in filtered
            if expected_norm in str(row.get(column, "")).strip().casefold()
        ]
    return filtered


def detect_columns(records: list[dict[str, Any]]) -> ColumnMap:
    headers = list(records[0].keys()) if records else []
    return ColumnMap(
        full_name=_find_column(headers, "full_name", "name", "influencer_name"),
        instagram_link=_find_column(headers, "instagram_link", "instagram", "profile_link", "link"),
        followers=_find_column(headers, "followers", "follower_count"),
        gender=_find_column(headers, "gender", "sex"),
        city=_find_column(headers, "city", "location_city"),
        state=_find_column(headers, "state", "region", "province"),
        language=_find_column(headers, "language", "languages"),
        age=_find_column(headers, "age"),
        age_group=_find_column(headers, "age_group", "age_range", "audience_age"),
        reach=_find_column(headers, "reach", "avg_reach", "average_reach"),
        engagement=_find_column(headers, "engagement", "engagements", "total_engagement"),
        likes=_find_column(headers, "likes", "avg_likes"),
        comments=_find_column(headers, "comments", "avg_comments"),
        shares=_find_column(headers, "shares", "avg_shares"),
        saves=_find_column(headers, "saves", "avg_saves"),
        video_reach=tuple(_find_metric_columns(headers, ("video", "reel"), ("reach",))),
        video_views=tuple(_find_metric_columns(headers, ("video", "reel"), ("view", "views"))),
        age_ratio_columns=_age_ratio_columns(headers),
    )


def _top_locations(records: list[dict[str, Any]], columns: ColumnMap) -> list[dict[str, Any]]:
    if not columns.city and not columns.state:
        return []
    locations = []
    for row in records:
        parts = [str(row.get(column, "")).strip() for column in (columns.city, columns.state) if column]
        parts = [part for part in parts if part]
        if parts:
            locations.append(", ".join(parts))
    total = len(locations)
    if not total:
        return []
    return [
        {"location": location, "count": count, "percentage": _percent(count, total)}
        for location, count in Counter(locations).most_common(5)
    ]


def _gender_ratio(records: list[dict[str, Any]], columns: ColumnMap, gender: str) -> float | None:
    if not columns.gender:
        return None
    genders = [str(row.get(columns.gender, "")).strip().casefold() for row in records]
    genders = [value for value in genders if value]
    if not genders:
        return None
    return _percent(sum(1 for value in genders if value == gender), len(genders))


def _age_ratio(records: list[dict[str, Any]], columns: ColumnMap, bucket: str) -> float | None:
    if bucket in columns.age_ratio_columns:
        values = [_to_percent(row.get(columns.age_ratio_columns[bucket])) for row in records]
        values = [value for value in values if value is not None]
        return _round(sum(values) / len(values)) if values else None

    if columns.age_group:
        groups = [str(row.get(columns.age_group, "")).strip() for row in records]
        groups = [group for group in groups if group]
        if groups:
            return _percent(sum(1 for group in groups if _bucket_from_text(group) == bucket), len(groups))

    if columns.age:
        ages = [_to_number(row.get(columns.age)) for row in records]
        ages = [age for age in ages if age is not None]
        if ages:
            return _percent(sum(1 for age in ages if _bucket_from_age(age) == bucket), len(ages))

    return None


def _engagement_rate(records: list[dict[str, Any]], columns: ColumnMap) -> float | None:
    if not columns.reach:
        return None
    total_reach = 0.0
    total_engagement = 0.0
    for row in records:
        reach = _to_number(row.get(columns.reach))
        if reach is None or reach <= 0:
            continue
        engagement = _to_number(row.get(columns.engagement)) if columns.engagement else None
        if engagement is None:
            parts = [columns.likes, columns.comments, columns.shares, columns.saves]
            values = [_to_number(row.get(column)) for column in parts if column]
            engagement = sum(value for value in values if value is not None)
        total_reach += reach
        total_engagement += engagement or 0
    if total_reach <= 0:
        return None
    return _percent(total_engagement, total_reach)


def _followers_summary(followers: list[float]) -> dict[str, Any]:
    if not followers:
        return {"total": 0, "average": None, "min": None, "max": None}
    return {
        "total": int(sum(followers)),
        "average": _round(sum(followers) / len(followers)),
        "min": int(min(followers)),
        "max": int(max(followers)),
    }


def _last_10_average(records: list[dict[str, Any]], columns: Iterable[str]) -> float | None:
    selected_columns = list(columns)[:10]
    if not selected_columns:
        return None
    values = []
    for row in records:
        for column in selected_columns:
            value = _to_number(row.get(column))
            if value is not None:
                values.append(value)
    return _round(sum(values) / len(values)) if values else None


def _find_column(headers: list[str], *candidates: str) -> str | None:
    normalized = {_normalize_header(header): header for header in headers}
    for candidate in candidates:
        if candidate in normalized:
            return normalized[candidate]
    for candidate in candidates:
        for normalized_header, header in normalized.items():
            if candidate in normalized_header:
                return header
    return None


def _find_metric_columns(headers: list[str], prefixes: tuple[str, ...], metrics: tuple[str, ...]) -> list[str]:
    matches = []
    for header in headers:
        normalized = _normalize_header(header)
        if any(prefix in normalized for prefix in prefixes) and any(metric in normalized for metric in metrics):
            matches.append(header)
    return sorted(matches, key=_natural_key)


def _age_ratio_columns(headers: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in headers:
        normalized = _normalize_header(header)
        for bucket in AGE_BUCKETS:
            compact_bucket = bucket.replace("+", "plus").replace("-", "_")
            if compact_bucket in normalized and ("ratio" in normalized or "percent" in normalized or "percentage" in normalized):
                result[bucket] = header
    return result


def _normalize_header(header: str) -> str:
    value = str(header).strip().casefold().replace("+", "plus")
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _natural_key(value: str) -> list[Any]:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", value)]


def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) if math.isfinite(float(value)) else None
    cleaned = str(value).strip().replace(",", "")
    multiplier = 1.0
    if cleaned.endswith("%"):
        cleaned = cleaned[:-1]
    elif cleaned.casefold().endswith("k"):
        multiplier = 1_000.0
        cleaned = cleaned[:-1]
    elif cleaned.casefold().endswith("m"):
        multiplier = 1_000_000.0
        cleaned = cleaned[:-1]
    try:
        number = float(cleaned) * multiplier
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _to_percent(value: Any) -> float | None:
    number = _to_number(value)
    if number is None:
        return None
    return _round(number * 100 if 0 <= number <= 1 else number)


def _bucket_from_text(value: str) -> str | None:
    normalized = _normalize_header(value)
    for bucket in AGE_BUCKETS:
        if bucket.replace("+", "plus").replace("-", "_") in normalized:
            return bucket
    return None


def _bucket_from_age(age: float) -> str | None:
    if 18 <= age <= 24:
        return "18-24"
    if 25 <= age <= 34:
        return "25-34"
    if 35 <= age <= 45:
        return "35-45"
    if age > 45:
        return "45+"
    return None


def _percent(numerator: float, denominator: float) -> float:
    return _round((numerator / denominator) * 100) if denominator else 0.0


def _round(value: float) -> float:
    return round(value, 2)
