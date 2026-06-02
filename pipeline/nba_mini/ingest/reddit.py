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
TOP_FEED_RSS_URL = "https://www.reddit.com/r/nba/top/.rss?t=day"
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
    body: str = ""
    """Self-text body of the post, when it has one.

    Link/highlight posts carry no real body (their title is the content), so
    this is empty for them. For self-text posts it's the unescaped, tag-stripped
    discussion text — a big chunk of discourse signal the title alone misses.
    The JSON ingest path doesn't populate it (it predates the field); only the
    RSS path fills it, which is the production default.
    """


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
# RSS path (live default)
# ---------------------------------------------------------------------------
#
# Reddit hard-blocks the anonymous `.json` endpoints with a 403 challenge page
# (UA tweaks don't help; the proper fix is a registered OAuth app). The public
# Atom feed at `/r/<sub>/top/.rss` still serves with 200 and no auth. It's a
# leaner payload — post titles, flair, timestamps, permalinks, but NO comment
# bodies or scores. Titles carry most of the discourse signal the clue prompt
# needs, so we accept the trade and surface empty `top_comments` / `score=0`.


# Reddit caps a single RSS listing at 100 entries. The default (no ``limit``)
# is only 25 — asking for 100 quadruples the pool for free. ``after=`` paging
# is broken on the RSS endpoint (it returns the same page), so 100/sub is the
# hard ceiling per feed; we take all of it.
RSS_LISTING_LIMIT = 100


def reddit_rss_url(subreddit: str = "nba", *, window: str = "day") -> str:
    """Top-of-``window`` Atom feed URL for a subreddit.

    ``window`` is Reddit's ``t`` param: ``day`` | ``week`` | ``month`` | ...
    We use ``week`` for the multi-day recency pool and ``day`` for the legacy
    single-day path. ``limit`` is pinned to the 100-entry ceiling (see
    ``RSS_LISTING_LIMIT``).
    """
    return (
        f"https://www.reddit.com/r/{subreddit}/top/.rss"
        f"?t={window}&limit={RSS_LISTING_LIMIT}"
    )


def _rss_window_for_days(window_days: int) -> str:
    """Pick the smallest Reddit ``t=`` feed that covers ``window_days``.

    Reddit's top feed is bucketed (``day`` | ``week`` | ``month`` | ...), and a
    given bucket only *contains* roughly that many days of posts. The
    multi-day digest then filters by exact timestamp, so the bucket only needs
    to be large enough to *reach back* far enough — picking a bigger bucket than
    necessary just adds older noise the filter discards.

    - ``<= 1`` day  -> ``day``
    - ``<= 7`` days -> ``week``
    - otherwise     -> ``month`` (covers up to ~31 days; the filter trims it)
    """
    if window_days <= 1:
        return "day"
    if window_days <= 7:
        return "week"
    return "month"


def fetch_yesterday_discourse_rss(
    today: date,
    *,
    subreddit: str = "nba",
    rss_text: str | None = None,
    cache_dir: Path | None = None,
) -> RedditDigest:
    """Return yesterday's discourse digest from the subreddit's Atom feed.

    This is the production default now that the `.json` endpoint 403s. The
    digest contract is preserved; fields the feed can't provide are filled
    with neutral defaults (``top_comments=[]``, ``score=0``,
    ``comment_count=0``).

    Args:
        today: Pipeline run date (US/Eastern). Yesterday is ``today - 1`` in ET;
            entries outside that ET-day window are filtered out.
        subreddit: Which subreddit's feed to read (default ``nba``).
        rss_text: Optional raw Atom XML. Tests pass a recorded string; when
            omitted, a live `requests` GET is issued (with on-disk cache).
        cache_dir: Where to cache the live response. Same resolution rules as
            the JSON path. Ignored when ``rss_text`` is given.

    Returns:
        A validated ``RedditDigest``, newest-first as the feed orders them.

    Raises:
        RedditIngestError (or subclass) on transport / parse failure.
    """
    yesterday = today - timedelta(days=1)
    yesterday_iso = yesterday.isoformat()

    if rss_text is None:
        resolved_cache = _resolve_cache_dir(cache_dir, yesterday_iso)
        rss_text = _live_rss_fetch(reddit_rss_url(subreddit), resolved_cache)

    start_utc, end_utc = _et_day_bounds_utc(yesterday)

    posts: list[RedditPost] = []
    for entry in _parse_rss_entries(rss_text):
        created = entry["created_utc"]
        # Some feed entries lack a parseable timestamp; keep them rather than
        # silently dropping signal (the feed is already "top of day").
        if created is not None and not (start_utc <= created < end_utc):
            continue
        posts.append(
            RedditPost(
                title=entry["title"] or "(untitled)",
                flair=entry["flair"],
                score=0,
                comment_count=0,
                top_comments=[],
                permalink=entry["permalink"],
                body=entry.get("body", ""),
            )
        )

    return RedditDigest(date=yesterday_iso, posts=posts)


def fetch_recent_discourse_rss(
    today: date,
    *,
    subreddits: list[str],
    window_days: int = 3,
    rss_by_sub: dict[str, str] | None = None,
    cache_dir: Path | None = None,
) -> RedditDigest:
    """Merge several subreddits' top-of-week feeds into one recency digest.

    Where :func:`fetch_yesterday_discourse_rss` reads a single subreddit's
    single-day feed, this reads *multiple* subreddits over a multi-day window —
    the wider, more-current discourse pool that produces better clues.

    Args:
        today: Pipeline run date (US/Eastern). The window is the ``window_days``
            ET-days strictly before ``today`` (i.e. ``[today-window_days,
            today)``), so "today" itself — partial and noisy — is excluded.
        subreddits: Subreddits to read, in priority order. The merged digest is
            deduped by permalink, first occurrence winning, so earlier
            subreddits in the list win ties.
        window_days: How many days back to include. Defaults to 3.
        rss_by_sub: Optional ``{subreddit: raw_atom_xml}`` for tests; when given,
            no network calls are made and only the listed subs are read.
        cache_dir: Where to cache live responses. Ignored when ``rss_by_sub``
            is given.

    Returns:
        A ``RedditDigest`` dated to the most recent day in the window
        (``today - 1``), with posts from every subreddit merged newest-first.

    Notes:
        Per-subreddit failures are isolated: a single sub that 403s, times out,
        or returns junk is logged and skipped rather than failing the whole
        batch. Only if *every* subreddit fails do we raise, since that's a real
        outage rather than one flaky feed.
    """
    if window_days > 7:
        # Past a week the only feed that reaches back far enough is ``month``,
        # whose top-100 are ranked over ~31 days — so the timestamp filter below
        # discards most of them and the *effective* pool shrinks rather than
        # grows (measured: 7d→160 surviving posts, 10d→66). This isn't a hard
        # error (the run still produces a digest), but it's a degradation worth
        # surfacing rather than hiding.
        logger.warning(
            "reddit: window_days=%d exceeds the 7-day RSS sweet spot; the feed "
            "falls back to the top-of-month bucket and the timestamp filter "
            "discards most of it, so the pool typically *shrinks*. Prefer <= 7.",
            window_days,
        )

    window_start = today - timedelta(days=window_days)
    window_end = today  # exclusive — excludes the partial current ET-day
    start_utc, _ = _et_day_bounds_utc(window_start)
    _, end_utc = _et_day_bounds_utc(window_end - timedelta(days=1))

    most_recent_iso = (today - timedelta(days=1)).isoformat()

    seen_permalinks: set[str] = set()
    merged: list[RedditPost] = []
    failures = 0
    for sub in subreddits:
        try:
            if rss_by_sub is not None:
                if sub not in rss_by_sub:
                    continue
                rss_text = rss_by_sub[sub]
            else:
                resolved_cache = _resolve_cache_dir(cache_dir, most_recent_iso)
                rss_text = _live_rss_fetch(
                    reddit_rss_url(sub, window=_rss_window_for_days(window_days)),
                    resolved_cache,
                )
            entries = _parse_rss_entries(rss_text)
        except RedditIngestError as e:
            failures += 1
            logger.warning("reddit: skipping r/%s — %s", sub, e)
            continue

        for entry in entries:
            created = entry["created_utc"]
            if created is not None and not (start_utc <= created < end_utc):
                continue
            permalink = entry["permalink"]
            if permalink in seen_permalinks:
                continue
            seen_permalinks.add(permalink)
            merged.append(
                RedditPost(
                    title=entry["title"] or "(untitled)",
                    flair=entry["flair"],
                    score=0,
                    comment_count=0,
                    top_comments=[],
                    permalink=permalink,
                    body=entry.get("body", ""),
                )
            )

    if failures and failures == len(subreddits):
        raise RedditNetworkError(
            f"all {failures} subreddit feed(s) failed: {', '.join(subreddits)}"
        )

    return RedditDigest(date=most_recent_iso, posts=merged)


# Atom namespace used by Reddit's RSS feed.
_ATOM_NS = "{http://www.w3.org/2005/Atom}"


def _parse_rss_entries(rss_text: str) -> list[dict]:
    """Parse Reddit Atom XML into a list of normalized entry dicts.

    Each dict has: title (str), flair (str|None), permalink (str),
    created_utc (float|None). Flair is parsed from a leading ``[Tag]`` in the
    title when present (the feed's <category> is just the subreddit name).
    """
    import xml.etree.ElementTree as ET  # noqa: PLC0415 — stdlib, lazy for symmetry

    try:
        root = ET.fromstring(rss_text)
    except ET.ParseError as e:
        raise RedditResponseError(f"reddit RSS is not valid XML: {e}") from e

    entries: list[dict] = []
    for el in root.findall(f"{_ATOM_NS}entry"):
        title_el = el.find(f"{_ATOM_NS}title")
        link_el = el.find(f"{_ATOM_NS}link")
        updated_el = el.find(f"{_ATOM_NS}updated")
        content_el = el.find(f"{_ATOM_NS}content")

        raw_title = (title_el.text or "").strip() if title_el is not None else ""
        permalink = ""
        if link_el is not None:
            href = link_el.get("href", "").strip()
            # Store the path portion to match the JSON path's permalink shape.
            permalink = href.replace(PERMALINK_BASE, "") if href else ""
        if not permalink:
            # An entry with no link is unusable as a clue anchor; skip it.
            continue

        flair, title = _split_flair_and_title(raw_title)
        entries.append(
            {
                "title": title,
                "flair": flair,
                "permalink": permalink,
                "body": _extract_selftext_body(
                    content_el.text if content_el is not None else None
                ),
                "created_utc": _parse_atom_timestamp(
                    updated_el.text if updated_el is not None else None
                ),
            }
        )
    return entries


# Reddit wraps a self-post's real body in these comment markers inside <content>.
# A link/highlight post has no such block — its <content> is just the
# "submitted by /u/... [link] [comments]" boilerplate, which carries no signal
# the title doesn't already have. So we only lift text found between the markers.
_SELFTEXT_OPEN = "<!-- SC_OFF -->"
_SELFTEXT_CLOSE = "<!-- SC_ON -->"
_MAX_BODY_CHARS = 1500


def _extract_selftext_body(content_html: str | None) -> str:
    """Pull a post's self-text body out of an RSS ``<content>`` block.

    Returns the unescaped, tag-stripped, whitespace-collapsed body for a
    self-text post, or ``""`` for a link/highlight post (whose content is just
    boilerplate). Truncated to ``_MAX_BODY_CHARS`` so one rambling post can't
    dominate the prompt budget.
    """
    if not content_html:
        return ""
    import html  # noqa: PLC0415 — stdlib, lazy for symmetry
    import re  # noqa: PLC0415

    start = content_html.find(_SELFTEXT_OPEN)
    end = content_html.find(_SELFTEXT_CLOSE)
    if start == -1 or end == -1 or end <= start:
        # No self-text block: link/highlight post. Title is the whole signal.
        return ""

    inner = content_html[start + len(_SELFTEXT_OPEN) : end]
    # Content is double-escaped (entity-encoded HTML). Unescape, strip tags,
    # unescape once more (tags themselves were entity-encoded), then collapse.
    inner = html.unescape(inner)
    inner = re.sub(r"<[^>]+>", " ", inner)
    inner = html.unescape(inner)
    inner = re.sub(r"\s+", " ", inner).strip()
    if len(inner) > _MAX_BODY_CHARS:
        inner = inner[:_MAX_BODY_CHARS].rsplit(" ", 1)[0] + "…"
    return inner


def _split_flair_and_title(raw_title: str) -> tuple[str | None, str]:
    """Split a leading ``[Tag]`` off a title into (flair, remaining_title).

    Reddit's RSS bakes the flair into the title as a ``[Post Game Thread]``
    prefix; the <category> element only carries the subreddit name. We lift
    the tag into `flair` and strip it from the title so the prompt doesn't see
    it twice. Titles without a tag return ``(None, title)`` unchanged.
    """
    s = raw_title.strip()
    if s.startswith("[") and "]" in s:
        close = s.index("]")
        flair = s[1:close].strip() or None
        title = s[close + 1 :].strip()
        return flair, (title or s)
    return None, s


def _parse_atom_timestamp(text: str | None) -> float | None:
    """Parse an Atom RFC-3339 timestamp into a UTC unix float, or None."""
    if not text:
        return None
    s = text.strip()
    # Python's fromisoformat handles the trailing 'Z' only from 3.11+; be safe.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _live_rss_fetch(url: str, cache_dir: Path) -> str:
    """Fetch raw Atom XML with on-disk cache + 429 backoff. Returns text."""
    import requests  # noqa: PLC0415 — lazy on purpose

    cache_path = cache_dir / (_cache_filename(url).removesuffix(".json") + ".rss")
    if cache_path.exists():
        return cache_path.read_text()

    headers = {"User-Agent": USER_AGENT}
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
                    url, sleep_for, attempt + 1, RATE_LIMIT_RETRIES,
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

        cache_path.write_text(resp.text)
        return resp.text

    assert last_exc is not None
    raise last_exc


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
