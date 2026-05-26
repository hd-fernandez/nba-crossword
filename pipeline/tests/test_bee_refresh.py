"""Tests for the corpus refresh / merge logic."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nba_mini.bee.refresh import (
    AUTO_BLOCK_HEADER_PREFIX,
    build_auto_block,
    diff_new_entries,
    existing_keys,
    refresh_corpus,
)
from nba_mini.bee.roster import RosterPlayer


# ---------------------------------------------------------------------------
# existing_keys
# ---------------------------------------------------------------------------


def test_existing_keys_extracts_name_type_pairs() -> None:
    body = """\
LEBRON|first_mononym|LeBron
JAMES|last|LeBron James
# this is a comment

CURRY|last|Steph Curry
"""
    assert existing_keys(body) == {
        ("LEBRON", "first_mononym"),
        ("JAMES", "last"),
        ("CURRY", "last"),
    }


def test_existing_keys_skips_malformed_lines() -> None:
    body = """\
LEBRON|first_mononym|LeBron
malformed line with no pipes
TWO|FIELDS
"""
    # Only the well-formed line survives.
    assert existing_keys(body) == {("LEBRON", "first_mononym")}


def test_existing_keys_handles_empty_input() -> None:
    assert existing_keys("") == set()


# ---------------------------------------------------------------------------
# diff_new_entries
# ---------------------------------------------------------------------------


def test_diff_filters_already_present() -> None:
    existing = {("JAMES", "last"), ("CURRY", "last")}
    incoming = [
        RosterPlayer(last_name="JAMES", display="LeBron James"),
        RosterPlayer(last_name="DONCIC", display="Luka Doncic"),
        RosterPlayer(last_name="CURRY", display="Steph Curry"),
    ]
    result = diff_new_entries(incoming, existing)
    assert [p.last_name for p in result] == ["DONCIC"]


def test_diff_dedupes_within_input() -> None:
    existing: set = set()
    incoming = [
        RosterPlayer(last_name="JAMES", display="LeBron James"),
        RosterPlayer(last_name="JAMES", display="Bronny James"),  # dup last
    ]
    result = diff_new_entries(incoming, existing)
    assert [p.display for p in result] == ["LeBron James"]


def test_diff_returns_empty_when_all_present() -> None:
    existing = {("JAMES", "last")}
    incoming = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    assert diff_new_entries(incoming, existing) == []


# ---------------------------------------------------------------------------
# build_auto_block
# ---------------------------------------------------------------------------


def test_build_auto_block_includes_dated_header() -> None:
    players = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    block = build_auto_block(players, today=date(2026, 5, 26))
    assert AUTO_BLOCK_HEADER_PREFIX in block
    assert "2026-05-26" in block


def test_build_auto_block_formats_each_player() -> None:
    players = [
        RosterPlayer(last_name="JAMES", display="LeBron James"),
        RosterPlayer(last_name="DONCIC", display="Luka Doncic"),
    ]
    block = build_auto_block(players, today=date(2026, 5, 26))
    assert "JAMES|last|LeBron James" in block
    assert "DONCIC|last|Luka Doncic" in block


def test_build_auto_block_empty_when_no_players() -> None:
    assert build_auto_block([], today=date(2026, 5, 26)) == ""


def test_build_auto_block_ends_with_newline() -> None:
    players = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    block = build_auto_block(players, today=date(2026, 5, 26))
    assert block.endswith("\n")


# ---------------------------------------------------------------------------
# refresh_corpus (file I/O)
# ---------------------------------------------------------------------------


def test_refresh_corpus_appends_new_entries(tmp_path: Path) -> None:
    p = tmp_path / "names_test.txt"
    p.write_text("# header\nLEBRON|first_mononym|LeBron\nJAMES|last|LeBron James\n")
    incoming = [
        RosterPlayer(last_name="JAMES", display="LeBron James"),  # already present
        RosterPlayer(last_name="DONCIC", display="Luka Doncic"),  # new
        RosterPlayer(last_name="CURRY", display="Steph Curry"),  # new
    ]
    appended = refresh_corpus(
        "nba", incoming, path=p, today=date(2026, 5, 26)
    )
    assert appended == 2
    body = p.read_text()
    assert "DONCIC|last|Luka Doncic" in body
    assert "CURRY|last|Steph Curry" in body
    # Existing content preserved
    assert "LEBRON|first_mononym|LeBron" in body
    assert "JAMES|last|LeBron James" in body


def test_refresh_corpus_is_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "names_test.txt"
    p.write_text("LEBRON|first_mononym|LeBron\n")
    incoming = [RosterPlayer(last_name="DONCIC", display="Luka Doncic")]

    first = refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))
    second = refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))
    third = refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))
    assert (first, second, third) == (1, 0, 0)
    # File should contain DONCIC exactly once.
    assert p.read_text().count("DONCIC|last|") == 1


def test_refresh_corpus_no_op_when_nothing_new(tmp_path: Path) -> None:
    p = tmp_path / "names_test.txt"
    p.write_text("JAMES|last|LeBron James\n")
    incoming = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    appended = refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))
    assert appended == 0
    # File unchanged
    assert p.read_text() == "JAMES|last|LeBron James\n"


def test_refresh_corpus_raises_when_corpus_missing(tmp_path: Path) -> None:
    p = tmp_path / "missing.txt"
    incoming = [RosterPlayer(last_name="JAMES", display="LeBron James")]
    with pytest.raises(FileNotFoundError):
        refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))


def test_refresh_corpus_handles_file_without_trailing_newline(
    tmp_path: Path,
) -> None:
    """A hand-edited corpus file might lack a trailing newline; the auto-
    block should still merge cleanly."""
    p = tmp_path / "names_test.txt"
    p.write_text("LEBRON|first_mononym|LeBron")  # no \n
    incoming = [RosterPlayer(last_name="DONCIC", display="Luka Doncic")]
    refresh_corpus("nba", incoming, path=p, today=date(2026, 5, 26))
    body = p.read_text()
    # The original line and the new entry are both present and parseable.
    assert "LEBRON|first_mononym|LeBron" in body
    assert "DONCIC|last|Luka Doncic" in body
