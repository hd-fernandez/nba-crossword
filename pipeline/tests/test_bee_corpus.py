"""Tests for the Bee names corpus loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from nba_mini.bee.corpus import (
    CorpusEntry,
    CorpusNotFoundError,
    corpus_path_for,
    load_corpus,
    names_only,
)


def write_corpus(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body)
    return p


# ---------------------------------------------------------------------------
# Real-corpus smoke tests
# ---------------------------------------------------------------------------


def test_real_nba_corpus_loads_with_entries() -> None:
    entries = load_corpus("nba")
    assert len(entries) > 50, f"expected a substantial NBA corpus; got {len(entries)}"
    # A few names we expect in any reasonable v3 starter corpus.
    names = names_only(entries)
    for must_have in ("LEBRON", "CURRY", "GIANNIS", "WEMBY", "JORDAN"):
        assert must_have in names, f"{must_have} missing from NBA corpus"


def test_real_wnba_corpus_loads_with_entries() -> None:
    entries = load_corpus("wnba")
    assert len(entries) > 30, f"expected a substantial WNBA corpus; got {len(entries)}"
    names = names_only(entries)
    for must_have in ("WILSON", "CLARK", "STEWART", "TAURASI"):
        assert must_have in names, f"{must_have} missing from WNBA corpus"


def test_corpus_entries_obey_length_window() -> None:
    for league in ("nba", "wnba"):
        for entry in load_corpus(league):
            assert 4 <= len(entry.name) <= 10, (
                f"{league} corpus has out-of-window name: {entry.name}"
            )


def test_corpus_names_are_uppercase_letters_only() -> None:
    for league in ("nba", "wnba"):
        for entry in load_corpus(league):
            assert entry.name.isupper() and entry.name.isalpha(), entry.name


def test_corpus_types_are_valid() -> None:
    valid = {"last", "first_mononym", "nickname"}
    for league in ("nba", "wnba"):
        for entry in load_corpus(league):
            assert entry.type in valid, (entry.name, entry.type)


# ---------------------------------------------------------------------------
# Loader-behavior tests against synthetic fixtures
# ---------------------------------------------------------------------------


def test_loader_skips_blank_and_comment_lines(tmp_path: Path) -> None:
    body = """\
# top comment
   # indented comment

LEBRON|first_mononym|LeBron
# trailing comment
JAMES|last|LeBron James
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    entries = load_corpus("nba", path=p)
    assert {e.name for e in entries} == {"LEBRON", "JAMES"}


def test_loader_drops_short_names(tmp_path: Path) -> None:
    body = """\
KD|first_mononym|KD
JOE|last|Joe Schmo
LEBRON|first_mononym|LeBron
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    entries = load_corpus("nba", path=p)
    # KD (2) and JOE (3) are below the 4-letter minimum; LEBRON (6) survives.
    assert {e.name for e in entries} == {"LEBRON"}


def test_loader_drops_overlong_names(tmp_path: Path) -> None:
    body = """\
ANTETOKOUNMPO|last|Giannis Antetokounmpo
KARLANTHONYTOWNS|last|Karl-Anthony Towns
LEBRON|first_mononym|LeBron
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    entries = load_corpus("nba", path=p)
    # Both >10 letters → filtered.
    assert {e.name for e in entries} == {"LEBRON"}


def test_loader_warns_on_malformed_lines(tmp_path: Path, caplog) -> None:
    body = """\
LEBRON|first_mononym|LeBron
BADROW_NO_PIPES
THREE|TYPE|TWO|EXTRA|FIELDS|HERE
JORDAN|last|Michael Jordan
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    with caplog.at_level("WARNING"):
        entries = load_corpus("nba", path=p)
    assert {e.name for e in entries} == {"LEBRON", "JORDAN"}
    # At least one warning should mention the skipped lines.
    assert any("skipped" in rec.message for rec in caplog.records)


def test_loader_rejects_unknown_type(tmp_path: Path, caplog) -> None:
    body = """\
LEBRON|first_mononym|LeBron
BADTYPE|sidekick|Bad Type
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    with caplog.at_level("WARNING"):
        entries = load_corpus("nba", path=p)
    assert {e.name for e in entries} == {"LEBRON"}


def test_loader_rejects_lowercase_or_punctuated_name(tmp_path: Path) -> None:
    body = """\
LEBRON|first_mononym|LeBron
lebron|first_mononym|LeBron lower
LE-BRON|first_mononym|LeBron hyphen
LE'BRON|first_mononym|LeBron apostrophe
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    entries = load_corpus("nba", path=p)
    # Only the uppercase A-Z form survives; punctuation must be stripped at
    # corpus-write time.
    assert [e.name for e in entries] == ["LEBRON"]


def test_loader_dedupes_by_name_and_type(tmp_path: Path) -> None:
    body = """\
LEBRON|first_mononym|LeBron
LEBRON|first_mononym|LeBron James (duplicate row)
LEBRON|last|LeBron James (different type, kept)
"""
    p = write_corpus(tmp_path, "names_test.txt", body)
    entries = load_corpus("nba", path=p)
    # First row of each (name, type) pair wins; (LEBRON, last) is a distinct
    # entry and is also kept.
    assert len(entries) == 2
    types = {(e.name, e.type) for e in entries}
    assert types == {("LEBRON", "first_mononym"), ("LEBRON", "last")}


def test_loader_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(CorpusNotFoundError):
        load_corpus("nba", path=tmp_path / "missing.txt")


def test_corpus_path_for_resolves_correctly() -> None:
    p = corpus_path_for("nba")
    assert p.name == "names_nba.txt"
    assert p.parent.name == "bee"


def test_names_only_returns_set_of_names() -> None:
    entries = [
        CorpusEntry(name="LEBRON", type="first_mononym", display="LeBron"),
        CorpusEntry(name="JAMES", type="last", display="LeBron James"),
        CorpusEntry(name="LEBRON", type="last", display="LeBron James"),
    ]
    assert names_only(entries) == {"LEBRON", "JAMES"}
