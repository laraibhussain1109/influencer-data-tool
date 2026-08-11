"""Instagram deliverable collection and comment sentiment analysis.

Instagram is rendered dynamically, so this module uses Instaloader rather than
HTML selectors.  Callers can inject a client, which keeps the collection logic
testable and allows another approved Instagram data provider to be substituted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
import re
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
DELIVERABLE_PATH = re.compile(r"^/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?")


class InstagramClient(Protocol):
    """Minimum interface required from an Instagram data provider."""

    def fetch(self, shortcode: str) -> dict[str, Any]: ...


@dataclass
class SentimentSummary:
    total_analyzed: int
    positive: int
    neutral: int
    negative: int
    average_compound: float | None


class InstaloaderClient:
    """Fetch public post metadata through Instaloader.

    Set ``INSTAGRAM_USERNAME`` and ``INSTAGRAM_SESSION_FILE`` to use an existing
    authenticated session. Password-based login is deliberately not performed.
    """

    def __init__(self, max_comments: int = 500) -> None:
        import instaloader

        self._instaloader = instaloader
        self._loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            save_metadata=False,
            compress_json=False,
            quiet=True,
        )
        self.max_comments = max_comments
        username = os.getenv("INSTAGRAM_USERNAME")
        session_file = os.getenv("INSTAGRAM_SESSION_FILE")
        if username and session_file:
            self._loader.load_session_from_file(username, session_file)

    def fetch(self, shortcode: str) -> dict[str, Any]:
        post = self._instaloader.Post.from_shortcode(self._loader.context, shortcode)
        comments = []
        for comment in post.get_comments():
            comments.append(comment.text)
            if len(comments) >= self.max_comments:
                break
        return {
            "likes": post.likes,
            "views": post.video_view_count if post.is_video else None,
            "comments_count": post.comments,
            "comments": comments,
        }


def shortcode_from_url(url: str) -> str:
    """Validate an Instagram deliverable URL and return its shortcode."""
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in INSTAGRAM_HOSTS:
        raise ValueError("Deliverable must be an Instagram http(s) URL.")
    match = DELIVERABLE_PATH.match(parsed.path)
    if not match:
        raise ValueError("URL must point to an Instagram post, reel, or IGTV deliverable.")
    return match.group(1)


def analyze_comments(
    comments: Iterable[str], analyzer: SentimentIntensityAnalyzer | None = None
) -> SentimentSummary:
    """Classify comments with VADER and return an aggregate summary."""
    sentiment = analyzer or SentimentIntensityAnalyzer()
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    scores: list[float] = []
    for comment in comments:
        text = str(comment).strip()
        if not text:
            continue
        compound = sentiment.polarity_scores(text)["compound"]
        scores.append(compound)
        label = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"
        counts[label] += 1
    return SentimentSummary(
        total_analyzed=len(scores),
        positive=counts["positive"],
        neutral=counts["neutral"],
        negative=counts["negative"],
        average_compound=round(sum(scores) / len(scores), 4) if scores else None,
    )


def collect_deliverable(url: str, client: InstagramClient) -> dict[str, Any]:
    """Collect engagement and sentiment for one deliverable URL."""
    shortcode = shortcode_from_url(url)
    raw = client.fetch(shortcode)
    summary = analyze_comments(raw.get("comments", []))
    return {
        "shortcode": shortcode,
        "likes": raw.get("likes"),
        "views": raw.get("views"),
        "comments": raw.get("comments_count"),
        "comments_collected": summary.total_analyzed,
        "sentiment": asdict(summary),
    }
