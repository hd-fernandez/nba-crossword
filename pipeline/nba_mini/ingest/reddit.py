"""r/nba ingest: yesterday's top posts + top comments → structured digest.

The output of this module is the *discourse* half of the generation context (the
other half being box scores). The generator picks candidate answers and frames
clue voice by reading this digest, so the shape here is the contract.

Tests do not hit live Reddit; they inject a fake fetcher pointed at recorded
fixtures under `pipeline/tests/fixtures/`. The live path uses `requests` with a
polite User-Agent and an on-disk per-date cache.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Callable

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

USER_AGENT = "nba-mini/0.1 by hd-fernandez"
TOP_FEED_URL = "https://www.reddit.com/r/nba/top.json?t=day&limit=50"
PERMALINK_BASE = "https://www.reddit.com"
DEFAULT_TOP_COMMENTS = 6
INTER_REQUEST_SLEEP_S = 1.0
RATE_LIMIT_RETRIES = 3
RATE_LIMIT_BACKOFF_BASE_S = 2.0

# US/Eastern day boundary: NBA's "day" lines up with ET. We approximate ET as a
# fixed UTC-4 offset (EDT) — the v0 puzzle runs in the season window where ET is
# always EDT, so we don't need a tz database for this. If the season ever runs
# through the Nov DST flip we revisit. Documented trade-off.
ET_OFFSET = timedelta(hours=-4)

# Fetcher signature: (url) -> parsed JSON. Lets tests inject a fake without
# touching `requests` and lets the live path stay a thin wrapper.
Fetcher = Callable[[str], object]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RedditIngestError(Exception):
    """Base error for any failure in the reddit ingest path.

    Callers should catch this rather than `requests` exceptions; the live
    fetcher wraps network errors into this type so the public surface stays
    transport-agnostic.
    """


class RedditRateLimitError(RedditIngestError):
    """429 from Reddit even after the retry-with-backoff budget."""


class RedditNetworkError(RedditIngestError):
    """Underlying transport failed (connection error, timeout, etc.)."""


class RedditResponseError(RedditIngestError):
    """Reddit returned an unexpected response shape we can't safely parse."""


# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class RedditPost(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: Annotated[str, Field(min_length=1)]
    flair: str | None
    score: int
    comment_count: int
    top_comments: list[str]
    permalink: Annotated[str, Field(min_length=1)]


class RedditDigest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    posts: list[RedditPost]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_yesterday_discourse(
    today: date,
    *,
    top_comments_per_post: int = DEFAULT_TOP_COMMENTS,
    fetcher: Fetcher | None = None,
    fixtures_dir: Path | None = None,
    cache_dir: Path | None = None,
    sleep_s: float = INTER_REQUEST_SLEEP_S,
) -> RedditDigest:
    """Return yesterday's r/nba discourse digest.

    Args:
        today: The date the pipeline is running for (US/Eastern). Yesterday is
            `today - 1 day` in ET; posts whose `created_utc` falls outside that
            ET-day window are filtered out.
        top_comments_per_post: How many top comments to pull per post.
        fetcher: Optional injected fetcher (URL -> parsed JSON). Tests pass a
            fake. If omitted, a live `requests`-based fetcher is built.
        fixtures_dir: Optional fixtures directory. If set, a fixture-replay
            fetcher is built that maps URLs to files in that directory:
              - top feed       → `reddit_top_posts.json`
              - permalink JSON → `reddit_comments_<post_id>.json`
            This is the cheapest way to wire tests without mocking `requests`.
        cache_dir: Where to cache live responses keyed by date. Defaults to
            `$NBA_MINI_CACHE_DIR/reddit/<date>` or
            `~/.cache/nba-mini/reddit/<date>`. Ignored when `fetcher` or
            `fixtures_dir` is set.
        sleep_s: Seconds to sleep between requests. Tests pass 0.

    Returns:
        A validated `RedditDigest` with one entry per "yesterday" post.

    Raises:
        RedditIngestError (or subclass) on any failure.
    """
    yesterday = today - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()

    if fixtures_dir is not None:
        chosen_fetcher: Fetcher = _fixtures_fetcher(fixtures_dir)
    elif fetcher is not None:
        chosen_fetcher = fetcher
    else:
        resolved_cache = _resolve_cache_dir(cache_dir, yesterday_iso)
        chosen_fetcher = _live_fetcher(resolved_cache)

    feed = chosen_fetcher(TOP_FEED_URL)
    children = _extract_children(feed, kind="t3")

    yesterday_start_utc, yesterday_end_utc = _et_day_bounds_utc(yesterday)

    posts: list[RedditPost] = []
    for i, child in enumerate(children):
        try:
            data = _require_dict(child, "post child").get("data")
            data_dict = _require_dict(data, "post data")
            created_utc = float(data_dict.get("created_utc", 0.0))
        except RedditResponseError:
            raise
        except (TypeError, ValueError) as e:
            raise RedditResponseError(f"post {i}: malformed created_utc: {e}") from e

        if not (yesterday_start_utc <= created_utc < yesterday_end_utc):
            continue

        permalink = str(data_dict.get("permalink", "")).strip()
        if not permalink:
            raise RedditResponseError(f"post {i}: missing permalink")

        # Politeness sleep before the per-post comments call.
        if posts and sleep_s > 0:
            time.sleep(sleep_s)

        comments_url = f"{PERMALINK_BASE}{permalink}.json"
        comments_payload = chosen_fetcher(comments_url)
        top_comments = _extract_top_comments(comments_payload, top_comments_per_post)

        posts.append(
            RedditPost(
                title=str(data_dict.get("title", "")).strip() or "(untitled)",
                flair=_optional_str(data_dict.get("link_flair_text")),
                score=int(data_dict.get("score", 0)),
                comment_count=int(data_dict.get("num_comments", 0)),
                top_comments=top_comments,
                permalink=permalink,
            )
        )

    return RedditDigest(date=yesterday_iso, posts=posts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _et_day_bounds_utc(yesterday_et: date) -> tuple[float, float]:
    """Return [start, end) UTC unix timestamps for the ET calendar day."""
    start_et = datetime.combine(yesterday_et, datetime.min.time())
    start_utc = (start_et - ET_OFFSET).replace(tzinfo=timezone.utc)
    end_utc = start_utc + timedelta(days=1)
    return start_utc.timestamp(), end_utc.timestamp()


def _optional_str(v: object) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _require_dict(v: object, label: str) -> dict:
    if not isinstance(v, dict):
        raise RedditResponseError(f"{label}: expected dict, got {type(v).__name__}")
    return v


def _extract_children(payload: object, *, kind: str) -> list[dict]:
    """Pull `data.children` from a Reddit Listing, filtered to `kind`."""
    listing = _require_dict(payload, "listing")
    data = _require_dict(listing.get("data"), "listing.data")
    raw_children = data.get("children")
    if not isinstance(raw_children, list):
        raise RedditResponseError("listing.data.children is not a list")
    return [c for c in raw_children if isinstance(c, dict) and c.get("kind") == kind]


def _extract_top_comments(payload: object, n: int) -> list[str]:
    """Pull up to `n` top comments from a permalink JSON payload.

    Reddit returns a 2-element list: [post_listing, comments_listing]. We pick
    the second; we skip "more" stubs and removed/deleted comment bodies.
    """
    if not isinstance(payload, list) or len(payload) < 2:
        raise RedditResponseError("permalink payload is not a 2-element list")

    children = _extract_children(payload[1], kind="t1")
    out: list[str] = []
    for c in children:
        if len(out) >= n:
            break
        data = _require_dict(c.get("data"), "comment data")
        body = data.get("body")
        if not isinstance(body, str):
            continue
        body_stripped = body.strip()
        if not body_stripped:
            continue
        if body_stripped in ("[deleted]", "[removed]"):
            continue
        out.append(body_stripped)
    return out


# ---------------------------------------------------------------------------
# Fetcher implementations
# ---------------------------------------------------------------------------


def _fixtures_fetcher(fixtures_dir: Path) -> Fetcher:
    """A fetcher that maps Reddit URLs to local fixture files.

    Mapping:
      - top feed → `reddit_top_posts.json`
      - permalink → `reddit_comments_<post_id>.json` where `<post_id>` is the
        path segment after `/comments/`.
    """
    fixtures_dir = Path(fixtures_dir)

    def _fetch(url: str) -> object:
        path = _fixture_path_for(fixtures_dir, url)
        if not path.exists():
            raise RedditResponseError(f"fixture missing for url={url}: {path}")
        return json.loads(path.read_text())

    return _fetch


def _fixture_path_for(fixtures_dir: Path, url: str) -> Path:
    if url.startswith(TOP_FEED_URL.split("?")[0]):
        return fixtures_dir / "reddit_top_posts.json"
    # Expected shape: https://www.reddit.com/r/nba/comments/<id>/<slug>/.json
    marker = "/comments/"
    if marker in url:
        rest = url.split(marker, 1)[1]
        post_id = rest.split("/", 1)[0]
        return fixtures_dir / f"reddit_comments_{post_id}.json"
    return fixtures_dir / "unknown.json"


def _resolve_cache_dir(cache_dir: Path | None, yesterday_iso: str) -> Path:
    if cache_dir is not None:
        base = Path(cache_dir)
    else:
        env = os.environ.get("NBA_MINI_CACHE_DIR")
        base = Path(env) if env else Path.home() / ".cache" / "nba-mini"
        base = base / "reddit"
    out = base / yesterday_iso
    out.mkdir(parents=True, exist_ok=True)
    return out


def _live_fetcher(cache_dir: Path) -> Fetcher:
    """A `requests`-based fetcher with on-disk cache + 429 backoff.

    Imported lazily so that fixture-only test runs don't require `requests`
    to be installed (it is, per pyproject, but the lazy import keeps the
    module importable in minimal environments).
    """
    import requests  # noqa: PLC0415 — lazy on purpose

    headers = {"User-Agent": USER_AGENT}

    def _fetch(url: str) -> object:
        cache_path = cache_dir / _cache_filename(url)
        if cache_path.exists():
            return json.loads(cache_path.read_text())

        last_exc: Exception | None = None
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                resp = requests.get(url, headers=headers, timeout=20)
            except requests.exceptions.RequestException as e:
                raise RedditNetworkError(f"network error fetching {url}: {e}") from e

            if resp.status_code == 429:
                if attempt < RATE_LIMIT_RETRIES:
                    sleep_for = RATE_LIMIT_BACKOFF_BASE_S * (2**attempt)
                    logger.warning(
                        "reddit 429 on %s, sleeping %.1fs (attempt %d/%d)",
                        url,
                        sleep_for,
                        attempt + 1,
                        RATE_LIMIT_RETRIES,
                    )
                    time.sleep(sleep_for)
                    continue
                last_exc = RedditRateLimitError(
                    f"rate limited on {url} after {RATE_LIMIT_RETRIES} retries"
                )
                break

            if resp.status_code >= 500:
                raise RedditNetworkError(f"reddit {resp.status_code} on {url}")
            if resp.status_code >= 400:
                raise RedditResponseError(f"reddit {resp.status_code} on {url}")

            try:
                payload = resp.json()
            except ValueError as e:
                raise RedditResponseError(f"non-JSON response from {url}: {e}") from e

            cache_path.write_text(json.dumps(payload))
            return payload

        assert last_exc is not None
        raise last_exc

    return _fetch


def _cache_filename(url: str) -> str:
    """Stable, filesystem-safe filename for a URL."""
    safe = url.replace("https://", "").replace("http://", "")
    safe = safe.replace("/", "_").replace("?", "_").replace("&", "_").replace("=", "_")
    return safe[:200] + ".json"
