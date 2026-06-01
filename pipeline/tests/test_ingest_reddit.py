"""Tests for r/nba ingest. Fixture-replay only — never hits live Reddit."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from nba_mini.ingest.reddit import (
    PERMALINK_BASE,
    TOP_FEED_URL,
    Fetcher,
    RedditDigest,
    RedditIngestError,
    RedditNetworkError,
    RedditRateLimitError,
    RedditResponseError,
    _split_flair_and_title,
    fetch_recent_discourse_rss,
    fetch_yesterday_discourse,
    fetch_yesterday_discourse_rss,
    reddit_rss_url,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The fixture is constructed against this date: posts dated to 2026-05-14 ET
# count as "yesterday" when today=2026-05-15. Post C is 2026-05-13 ET and must
# be excluded.
TODAY = date(2026, 5, 15)
YESTERDAY_ISO = "2026-05-14"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_fixture_replay() -> None:
    digest = fetch_yesterday_discourse(
        TODAY,
        fixtures_dir=FIXTURES,
        sleep_s=0,
    )

    assert isinstance(digest, RedditDigest)
    assert digest.date == YESTERDAY_ISO

    # Three "yesterday" posts; the older Post C is filtered out.
    assert len(digest.posts) == 3
    titles = [p.title for p in digest.posts]
    assert any("Lakers defeat the Celtics" in t for t in titles)
    assert any("LeBron's 40th point" in t for t in titles)
    assert any("Wemby" in t for t in titles)
    assert not any("Old discussion thread" in t for t in titles)


def test_happy_path_top_comments_capped_per_post() -> None:
    digest = fetch_yesterday_discourse(
        TODAY,
        fixtures_dir=FIXTURES,
        top_comments_per_post=4,
        sleep_s=0,
    )

    by_id = {p.permalink: p for p in digest.posts}
    post_a = next(p for k, p in by_id.items() if "post_a" in k)
    # post_a fixture has 4 valid comments + [deleted] + [removed] + a "more" stub.
    # With cap=4 we should get exactly 4 valid bodies, no placeholders.
    assert len(post_a.top_comments) == 4
    for body in post_a.top_comments:
        assert body not in ("[deleted]", "[removed]")
        assert body.strip() != ""


def test_post_fields_round_trip() -> None:
    digest = fetch_yesterday_discourse(TODAY, fixtures_dir=FIXTURES, sleep_s=0)
    post_a = next(p for p in digest.posts if "post_a" in p.permalink)

    assert post_a.flair == "Post Game Thread"
    assert post_a.score == 4821
    assert post_a.comment_count == 3120
    assert post_a.permalink.startswith("/r/nba/comments/post_a/")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_post_from_two_days_ago_is_excluded() -> None:
    """The fixture intentionally includes a 2026-05-13 ET post that must drop."""
    digest = fetch_yesterday_discourse(TODAY, fixtures_dir=FIXTURES, sleep_s=0)
    # Post C is the only one with permalink containing "post_c_old".
    assert not any("post_c_old" in p.permalink for p in digest.posts)


def test_removed_and_deleted_comments_are_skipped_not_crashed_on() -> None:
    """post_a includes one [deleted] and one [removed] comment body."""
    digest = fetch_yesterday_discourse(TODAY, fixtures_dir=FIXTURES, sleep_s=0)
    post_a = next(p for p in digest.posts if "post_a" in p.permalink)

    assert "[deleted]" not in post_a.top_comments
    assert "[removed]" not in post_a.top_comments
    # And there's at least one real comment so we know we didn't drop them all.
    assert len(post_a.top_comments) >= 1


def test_yesterday_window_is_exclusive_of_today() -> None:
    """A post timestamped at the start of *today* ET should be excluded."""
    # Build a one-post listing with created_utc at 2026-05-15 04:00 UTC =
    # 2026-05-15 00:00 ET (today, not yesterday).
    today_start_utc = 1778817600.0
    fake_top = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "post_today",
                        "title": "today's post",
                        "link_flair_text": None,
                        "score": 1,
                        "num_comments": 0,
                        "permalink": "/r/nba/comments/post_today/today/",
                        "created_utc": today_start_utc,
                    },
                }
            ]
        },
    }

    def fake_fetcher(url: str) -> object:
        if url == TOP_FEED_URL:
            return fake_top
        raise AssertionError(f"unexpected url: {url}")

    digest = fetch_yesterday_discourse(TODAY, fetcher=fake_fetcher, sleep_s=0)
    assert digest.posts == []


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_429_retried_with_backoff_then_raises_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live fetcher: 429 hammered the whole budget → typed RateLimit error."""
    # Stub `time.sleep` so the test doesn't actually wait for backoff.
    sleeps: list[float] = []

    import nba_mini.ingest.reddit as mod

    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))

    # Build a fake `requests` module returning 429 every time.
    class FakeResp:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def json(self) -> object:  # pragma: no cover - never reached
            return {}

    call_count = {"n": 0}

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResp:
        call_count["n"] += 1
        return FakeResp(429)

    fake_requests = type(
        "fake_requests",
        (),
        {
            "get": staticmethod(fake_get),
            "exceptions": type(
                "exc",
                (),
                {"RequestException": Exception},
            ),
        },
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    with pytest.raises(RedditRateLimitError):
        fetch_yesterday_discourse(
            TODAY,
            cache_dir=tmp_path,
            sleep_s=0,
        )

    # We should have retried RATE_LIMIT_RETRIES times → call_count > 1.
    assert call_count["n"] == mod.RATE_LIMIT_RETRIES + 1
    # And we should have slept between retries (RATE_LIMIT_RETRIES sleeps).
    assert len(sleeps) == mod.RATE_LIMIT_RETRIES


def test_network_error_raises_typed_exception(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Live fetcher: a transport error wraps to RedditNetworkError, not raw requests."""
    import nba_mini.ingest.reddit as mod

    class FakeRequestException(Exception):
        pass

    def boom(url: str, headers: dict, timeout: int) -> object:
        raise FakeRequestException("connection refused")

    fake_requests = type(
        "fake_requests",
        (),
        {
            "get": staticmethod(boom),
            "exceptions": type(
                "exc",
                (),
                {"RequestException": FakeRequestException},
            ),
        },
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)

    with pytest.raises(RedditNetworkError):
        fetch_yesterday_discourse(TODAY, cache_dir=tmp_path, sleep_s=0)


def test_unexpected_response_shape_is_typed_response_error() -> None:
    """If Reddit returns something that isn't a Listing, we raise cleanly."""

    def bogus(url: str) -> object:
        return {"kind": "not-a-listing", "data": "string instead of dict"}

    with pytest.raises(RedditResponseError):
        fetch_yesterday_discourse(TODAY, fetcher=bogus, sleep_s=0)


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


def test_live_fetcher_caches_response_to_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Second call for the same URL should hit cache, not the network."""
    import nba_mini.ingest.reddit as mod

    # Two URLs are fetched by happy-path: top feed + one permalink. Build a
    # minimal one-post listing so the test is self-contained.
    yesterday_post_ts = 1778810400.0
    top_payload = {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "p1",
                        "title": "t",
                        "link_flair_text": None,
                        "score": 1,
                        "num_comments": 0,
                        "permalink": "/r/nba/comments/p1/t/",
                        "created_utc": yesterday_post_ts,
                    },
                }
            ]
        },
    }
    permalink_payload = [
        {"kind": "Listing", "data": {"children": []}},
        {"kind": "Listing", "data": {"children": []}},
    ]

    call_count = {"n": 0}

    class FakeResp:
        def __init__(self, payload: object) -> None:
            self.status_code = 200
            self._payload = payload

        def json(self) -> object:
            return self._payload

    def fake_get(url: str, headers: dict, timeout: int) -> FakeResp:
        call_count["n"] += 1
        if url == TOP_FEED_URL:
            return FakeResp(top_payload)
        return FakeResp(permalink_payload)

    fake_requests = type(
        "fake_requests",
        (),
        {
            "get": staticmethod(fake_get),
            "exceptions": type("exc", (), {"RequestException": Exception}),
        },
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)

    d1 = fetch_yesterday_discourse(TODAY, cache_dir=tmp_path, sleep_s=0)
    first_calls = call_count["n"]
    d2 = fetch_yesterday_discourse(TODAY, cache_dir=tmp_path, sleep_s=0)

    # Second invocation should not have made any new HTTP calls.
    assert call_count["n"] == first_calls
    assert d1.model_dump() == d2.model_dump()


# ---------------------------------------------------------------------------
# Misc sanity
# ---------------------------------------------------------------------------


def test_subclasses_of_reddit_ingest_error() -> None:
    """All typed errors should be catchable via the base class."""
    for cls in (RedditNetworkError, RedditRateLimitError, RedditResponseError):
        assert issubclass(cls, RedditIngestError)


def test_fixture_files_exist_and_parse() -> None:
    """Guards against accidental fixture rot."""
    for name in (
        "reddit_top_posts.json",
        "reddit_comments_post_a.json",
        "reddit_comments_post_b.json",
        "reddit_comments_post_d.json",
    ):
        path = FIXTURES / name
        assert path.exists(), f"missing fixture: {name}"
        json.loads(path.read_text())  # raises if malformed


def test_fetcher_type_alias_is_callable() -> None:
    """Tiny smoke that the public Fetcher alias matches what tests pass."""
    f: Fetcher = lambda url: {"kind": "Listing", "data": {"children": []}}  # noqa: E731
    assert callable(f)


def test_permalink_base_constant_used_for_comments_url() -> None:
    """Verify the URL we'd build matches Reddit's permalink convention."""
    permalink = "/r/nba/comments/x/y/"
    expected = f"{PERMALINK_BASE}{permalink}.json"
    assert expected == "https://www.reddit.com/r/nba/comments/x/y/.json"


# ---------------------------------------------------------------------------
# RSS path (live production default — fixture-replay here, no network)
# ---------------------------------------------------------------------------

RSS_FIXTURE = (FIXTURES / "reddit_top.rss").read_text()


def test_rss_happy_path_filters_to_yesterday() -> None:
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=RSS_FIXTURE)
    assert isinstance(digest, RedditDigest)
    assert digest.date == YESTERDAY_ISO
    titles = [p.title for p in digest.posts]
    # Three yesterday posts; the two-days-ago entry and the link-less entry drop.
    assert any("Lakers defeat the Celtics" in t for t in titles)
    assert any("LeBron's 40th point" in t for t in titles)
    assert any("Wemby" in t for t in titles)
    assert not any("Old discussion thread" in t for t in titles)
    assert not any("no link" in t for t in titles)


def test_rss_lifts_flair_out_of_title() -> None:
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=RSS_FIXTURE)
    by_flair = {p.flair: p for p in digest.posts}
    assert "Post Game Thread" in by_flair
    pgt = by_flair["Post Game Thread"]
    # Flair tag stripped from the title, not duplicated.
    assert pgt.title == "The Lakers defeat the Celtics 118-114"
    assert "[Post Game Thread]" not in pgt.title


def test_rss_untagged_title_has_no_flair() -> None:
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=RSS_FIXTURE)
    wemby = next(p for p in digest.posts if "Wemby" in p.title)
    assert wemby.flair is None
    assert wemby.title == "Wemby pulls up in a thobe"


def test_rss_neutral_defaults_for_unavailable_fields() -> None:
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=RSS_FIXTURE)
    for p in digest.posts:
        assert p.top_comments == []
        assert p.score == 0
        assert p.comment_count == 0
        assert p.permalink.startswith("/r/nba/comments/")


def test_rss_permalink_is_path_only() -> None:
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=RSS_FIXTURE)
    for p in digest.posts:
        assert not p.permalink.startswith("http")


def test_rss_invalid_xml_raises_response_error() -> None:
    with pytest.raises(RedditResponseError, match="not valid XML"):
        fetch_yesterday_discourse_rss(TODAY, rss_text="<not-closed")


def test_rss_empty_feed_yields_empty_digest() -> None:
    empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
    digest = fetch_yesterday_discourse_rss(TODAY, rss_text=empty)
    assert digest.posts == []
    assert digest.date == YESTERDAY_ISO


def test_split_flair_and_title_variants() -> None:
    assert _split_flair_and_title("[Highlight] Big dunk") == ("Highlight", "Big dunk")
    assert _split_flair_and_title("No tag here") == (None, "No tag here")
    # A title that is only a tag keeps the original as the title fallback.
    flair, title = _split_flair_and_title("[OC]")
    assert flair == "OC"
    assert title  # non-empty


def test_reddit_rss_url_defaults_to_nba() -> None:
    assert reddit_rss_url() == "https://www.reddit.com/r/nba/top/.rss?t=day"
    assert reddit_rss_url("wnba") == "https://www.reddit.com/r/wnba/top/.rss?t=day"


def test_reddit_rss_url_window_param() -> None:
    assert (
        reddit_rss_url("nbatalk", window="week")
        == "https://www.reddit.com/r/nbatalk/top/.rss?t=week"
    )


# ---------------------------------------------------------------------------
# Multi-subreddit, multi-day recency digest
# ---------------------------------------------------------------------------


def test_recent_window_keeps_days_a_single_day_drops() -> None:
    # The single-day path drops the 2026-05-13 "Old discussion thread"; a 3-day
    # window ending 2026-05-15 (i.e. [05-12, 05-15)) must keep it.
    digest = fetch_recent_discourse_rss(
        TODAY, subreddits=["nba"], window_days=3, rss_by_sub={"nba": RSS_FIXTURE}
    )
    titles = [p.title for p in digest.posts]
    assert any("Old discussion thread" in t for t in titles)
    assert any("Lakers defeat the Celtics" in t for t in titles)
    # Dated to the most recent day in the window (yesterday).
    assert digest.date == YESTERDAY_ISO


def test_recent_window_merges_and_dedups_by_permalink() -> None:
    # The same fixture served from two subs: every permalink is a duplicate, so
    # the merged post count equals the single-sub count (no doubling).
    one = fetch_recent_discourse_rss(
        TODAY, subreddits=["nba"], window_days=3, rss_by_sub={"nba": RSS_FIXTURE}
    )
    merged = fetch_recent_discourse_rss(
        TODAY,
        subreddits=["nba", "nbatalk"],
        window_days=3,
        rss_by_sub={"nba": RSS_FIXTURE, "nbatalk": RSS_FIXTURE},
    )
    assert len(merged.posts) == len(one.posts)
    permalinks = [p.permalink for p in merged.posts]
    assert len(permalinks) == len(set(permalinks))


def test_recent_window_isolates_per_sub_failure() -> None:
    # A sub absent from rss_by_sub is simply skipped (treated as no data), so a
    # single missing/bad feed doesn't sink the batch.
    digest = fetch_recent_discourse_rss(
        TODAY,
        subreddits=["nba", "deadsub"],
        window_days=3,
        rss_by_sub={"nba": RSS_FIXTURE},  # "deadsub" missing
    )
    assert digest.posts  # still got nba's posts
    assert digest.date == YESTERDAY_ISO
