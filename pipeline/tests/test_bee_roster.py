"""Tests for the Bee roster fetcher + normalizer."""

from __future__ import annotations

import pytest

from nba_mini.bee.roster import (
    RosterClient,
    RosterFetchError,
    RosterPlayer,
    fetch_roster,
    normalize_last_name,
    to_corpus_lines,
)


class StubClient:
    """Test stand-in for RosterClient. Returns canned rows."""

    def __init__(self, rows: list[tuple[str, bool]]):
        self.rows = rows
        self.calls: list[tuple[str, bool]] = []

    def fetch(self, league, *, only_active):
        self.calls.append((league, only_active))
        return self.rows


# ---------------------------------------------------------------------------
# normalize_last_name
# ---------------------------------------------------------------------------


def test_normalize_basic_first_last() -> None:
    assert normalize_last_name("LeBron James") == "JAMES"


def test_normalize_strips_diacritics() -> None:
    assert normalize_last_name("Luka Dončić") == "DONCIC"
    assert normalize_last_name("Alperen Şengün") == "SENGUN"


def test_normalize_strips_punctuation() -> None:
    assert normalize_last_name("Shaquille O'Neal") == "ONEAL"
    assert normalize_last_name("Karl-Anthony Towns") == "TOWNS"


def test_normalize_strips_jr_suffix() -> None:
    # Junior on the end should peel off, leaving the real last name.
    assert normalize_last_name("Jaren Jackson Jr.") == "JACKSON"
    assert normalize_last_name("Tim Hardaway Jr") == "HARDAWAY"


def test_normalize_strips_sr_and_roman_numerals() -> None:
    assert normalize_last_name("Larry Nance Sr.") == "NANCE"
    assert normalize_last_name("Robert Williams III") == "WILLIAMS"


def test_normalize_drops_too_short() -> None:
    # Last name only 2 letters -> below the 4-letter floor.
    assert normalize_last_name("Yao Ming") == "MING"  # 4 chars, on the boundary
    assert normalize_last_name("Ming Yi") is None  # last name "YI" -> too short


def test_normalize_drops_too_long() -> None:
    # 13 letters -> above the 10-letter ceiling.
    assert normalize_last_name("Giannis Antetokounmpo") is None


def test_normalize_returns_none_for_empty_or_invalid() -> None:
    assert normalize_last_name("") is None
    assert normalize_last_name("   ") is None
    assert normalize_last_name(None) is None  # type: ignore[arg-type]


def test_normalize_handles_single_name() -> None:
    # Input with no whitespace — unusual but possible.
    assert normalize_last_name("Pelle") == "PELLE"


# ---------------------------------------------------------------------------
# fetch_roster
# ---------------------------------------------------------------------------


def test_fetch_roster_passes_through_normalized_names() -> None:
    client = StubClient([
        ("LeBron James", True),
        ("Luka Dončić", True),
        ("Shaquille O'Neal", False),
    ])
    out = fetch_roster("nba", client=client)
    assert [p.last_name for p in out] == ["JAMES", "DONCIC", "ONEAL"]
    # Display preserves the original casing/punctuation
    assert out[1].display == "Luka Dončić"


def test_fetch_roster_dedupes_by_last_name() -> None:
    client = StubClient([
        ("LeBron James", True),
        ("Bronny James", True),  # same last name → deduped
        ("Luka Dončić", True),
    ])
    out = fetch_roster("nba", client=client)
    assert [p.last_name for p in out] == ["JAMES", "DONCIC"]


def test_fetch_roster_drops_unnormalizable() -> None:
    client = StubClient([
        ("LeBron James", True),
        ("Yi Ming", True),  # last name "MING" is fine, 4 letters
        ("Yi Yi", True),  # last name "YI" is too short
        ("", True),  # empty
        ("Giannis Antetokounmpo", True),  # too long
    ])
    out = fetch_roster("nba", client=client)
    assert [p.last_name for p in out] == ["JAMES", "MING"]


def test_fetch_roster_threads_only_active_flag() -> None:
    client = StubClient([])
    fetch_roster("wnba", only_active=True, client=client)
    fetch_roster("wnba", only_active=False, client=client)
    assert client.calls == [("wnba", True), ("wnba", False)]


def test_fetch_roster_handles_empty_response() -> None:
    client = StubClient([])
    assert fetch_roster("nba", client=client) == []


# ---------------------------------------------------------------------------
# to_corpus_lines
# ---------------------------------------------------------------------------


def test_to_corpus_lines_formats_correctly() -> None:
    players = [
        RosterPlayer(last_name="JAMES", display="LeBron James"),
        RosterPlayer(last_name="DONCIC", display="Luka Dončić"),
    ]
    lines = to_corpus_lines(players)
    assert lines == [
        "JAMES|last|LeBron James",
        "DONCIC|last|Luka Dončić",
    ]


def test_to_corpus_lines_no_trailing_newlines() -> None:
    players = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    lines = to_corpus_lines(players)
    assert "\n" not in lines[0]


# ---------------------------------------------------------------------------
# Error path
# ---------------------------------------------------------------------------


def test_default_client_raises_when_nba_api_missing(monkeypatch) -> None:
    """The lazy-import path should raise RosterFetchError, not ImportError,
    so callers can handle it as a typed roster issue."""
    import builtins

    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name.startswith("nba_api"):
            raise ImportError("nba_api not installed (simulated)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from nba_mini.bee.roster import NbaApiRosterClient

    client = NbaApiRosterClient()
    with pytest.raises(RosterFetchError):
        client.fetch("nba", only_active=True)
