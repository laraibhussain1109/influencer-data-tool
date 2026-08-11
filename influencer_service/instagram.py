"""Instagram deliverable collection and comment sentiment analysis.

Instagram is rendered dynamically, so this module uses Instaloader rather than
HTML selectors.  Callers can inject a client, which keeps the collection logic
testable and allows another approved Instagram data provider to be substituted.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import re
from typing import Any, Iterable, Protocol
from urllib.parse import urlparse

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


INSTAGRAM_HOSTS = {"instagram.com", "www.instagram.com"}
DELIVERABLE_PATH = re.compile(r"^/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?")
CHECKPOINT_PATH = re.compile(r"(/(?:auth_platform|challenge)/\?[^\s]+)")


class InstagramAuthenticationError(RuntimeError):
    """Raised when Instagram requires account action before collection can continue."""


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

    Set ``INSTAGRAM_USERNAME`` and ``INSTAGRAM_PASSWORD`` to log in.  When
    ``INSTAGRAM_SESSION_FILE`` is also set, a valid saved session is reused and a
    newly authenticated session is saved there.  Credentials are read only from
    the environment so they do not leak into workbooks, command history, or API
    payloads.
    """

    def __init__(self, max_comments: int = 500, browser_login: bool = False) -> None:
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
            # Instagram sometimes returns HTTP 200 with a JSON "fail" payload for
            # comments. Do not let Instaloader retry every post indefinitely.
            max_connection_attempts=1,
        )
        self.max_comments = max_comments
        username = os.getenv("INSTAGRAM_USERNAME")
        password = os.getenv("INSTAGRAM_PASSWORD")
        session_file = _session_file_path(username, os.getenv("INSTAGRAM_SESSION_FILE"))
        if browser_login:
            self._authenticate_with_browser(username, session_file)
        else:
            self._authenticate(username, password, session_file)

    def _authenticate_with_browser(self, username: str | None, session_file: str | None) -> None:
        """Open Chrome for a manual login and copy its cookies into Instaloader."""
        if not username:
            raise InstagramAuthenticationError(
                "Browser login requires INSTAGRAM_USERNAME and INSTAGRAM_SESSION_FILE."
            )
        if not session_file:
            raise InstagramAuthenticationError(
                "Browser login requires INSTAGRAM_SESSION_FILE so the approved session can be saved."
            )

        from selenium import webdriver

        options = webdriver.ChromeOptions()
        profile_dir = os.getenv("INSTAGRAM_CHROME_PROFILE_DIR")
        if profile_dir:
            options.add_argument(f"--user-data-dir={profile_dir}")
        browser = webdriver.Chrome(options=options)
        try:
            browser.get("https://www.instagram.com/accounts/login/")
            input(
                "Complete the Instagram login/checkpoint in Chrome. "
                "When your Instagram home page is visible, press Enter here..."
            )
            cookies = {item["name"]: item["value"] for item in browser.get_cookies()}
            if not cookies.get("sessionid"):
                raise InstagramAuthenticationError(
                    "Chrome does not contain an Instagram session. Complete login before pressing Enter."
                )
            self._loader.context.update_cookies(cookies)
            logged_in_as = self._loader.test_login()
            if not logged_in_as or logged_in_as.casefold() != username.casefold():
                raise InstagramAuthenticationError(
                    f"Chrome is logged in as {logged_in_as or 'an unknown account'}, not {username}."
                )
            # update_cookies() authenticates requests, but Instaloader also checks this
            # field before save_session_to_file().  login() and load_session_from_file()
            # normally set it; a Selenium cookie transfer must do so explicitly.
            self._loader.context.username = logged_in_as
            self._loader.save_session_to_file(session_file)
        finally:
            browser.quit()

    def _authenticate(
        self, username: str | None, password: str | None, session_file: str | None
    ) -> None:
        """Reuse a session when possible, otherwise perform an Instagram login."""
        if not username:
            raise InstagramAuthenticationError(
                "Instagram login is required for comments. Set INSTAGRAM_USERNAME and "
                "INSTAGRAM_PASSWORD (and optionally INSTAGRAM_SESSION_FILE)."
            )

        if session_file:
            try:
                self._loader.load_session_from_file(username, session_file)
                if self._loader.test_login() == username:
                    return
            except (FileNotFoundError, self._instaloader.exceptions.LoginException):
                # Missing, expired, or invalid sessions are refreshed using the password below.
                pass

        if not password:
            raise InstagramAuthenticationError(
                "No valid Instagram session was found. Set INSTAGRAM_PASSWORD to log in "
                "and refresh the session."
            )
        try:
            self._loader.login(username, password)
        except self._instaloader.exceptions.LoginException as error:
            raise InstagramAuthenticationError(_login_error_message(error)) from error

        if session_file:
            self._loader.save_session_to_file(session_file)

    def fetch(self, shortcode: str) -> dict[str, Any]:
        post = self._instaloader.Post.from_shortcode(self._loader.context, shortcode)
        comments = []
        comments_error = None
        if self.max_comments:
            try:
                for comment in post.get_comments():
                    comments.append(comment.text)
                    if len(comments) >= self.max_comments:
                        break
            except self._instaloader.exceptions.InstaloaderException as error:
                # Preserve likes/views/the total comment count when Instagram's
                # private comments endpoint is temporarily unavailable.
                comments_error = (
                    "Instagram did not return comment text. Engagement metrics were collected, "
                    f"but sentiment is unavailable: {error}"
                )
        return {
            "likes": post.likes,
            "views": post.video_view_count if post.is_video else None,
            "comments_count": post.comments,
            "comments": comments,
            "comments_error": comments_error,
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
        "warning": raw.get("comments_error"),
    }


def _login_error_message(error: Exception) -> str:
    """Turn an Instaloader login failure into actionable, checkpoint-safe guidance."""
    detail = str(error)
    checkpoint = CHECKPOINT_PATH.search(detail)
    if checkpoint:
        url = f"https://www.instagram.com{checkpoint.group(1)}"
        return (
            "Instagram blocked the automated login with a security checkpoint. Open this "
            f"URL in a browser where the same account is signed in and approve it: {url}\n"
            "Then run the collector again. Keep INSTAGRAM_SESSION_FILE configured so the "
            "approved session is saved and reused. This security check cannot be bypassed "
            "programmatically. Alternatively, run the same command with --browser-login "
            "to complete the checkpoint interactively in Chrome and save its session."
        )
    return f"Instagram login failed: {detail}"


def _session_file_path(username: str | None, configured: str | None) -> str | None:
    """Accept either a session filename or an existing directory."""
    if not configured:
        return None
    path = Path(configured).expanduser()
    if path.is_dir():
        safe_username = re.sub(r"[^A-Za-z0-9_.-]", "_", username or "instagram")
        path = path / f"session-{safe_username}"
    return str(path)
