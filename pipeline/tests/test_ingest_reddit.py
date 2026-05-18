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
    fetch_yesterday_discourse,
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
