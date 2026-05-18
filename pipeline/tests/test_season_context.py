"""Tests for the season context loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from nba_mini.season_context import (
    DEFAULT_PATH,
    VERSION_HASH_LENGTH,
    SeasonContext,
    SeasonContextNotFoundError,
    load_season_context,
)


def test_default_loader_returns_non_empty_text_and_version() -> None:
    ctx = load_season_context()
    assert isinstance(ctx, SeasonContext)
    assert ctx.text.strip(), "season context text should not be empty"
    assert len(ctx.version) == VERSION_HASH_LENGTH
    # Hex chars only.
    int(ctx.version, 16)


def test_default_loader_mentions_current_phase_keywords() -> None:
    """Sanity check that the May 2026 snippet covers the storylines the plan calls out.

    Not a content lock — just ensures we don't ship an empty/placeholder file.
    """
    ctx = load_season_context()
    body = ctx.text.lower()
    assert "semi" in body, "expected a Conference Semis reference"
    assert "lottery" in body, "expected a Draft Lottery reference"
    assert "wemb" in body, "expected a Wembanyama reference"


def test_version_is_stable_for_unchanged_content() -> None:
    a = load_season_context()
    b = load_season_context()
    assert a.version == b.version
    assert a.text == b.text


def test_version_changes_when_content_changes(tmp_path: Path) -> None:
    f = tmp_path / "ctx.md"
    f.write_text("first version of the season context\n", encoding="utf-8")
    first = load_season_context(f)

    f.write_text("first version of the season context, plus an edit\n", encoding="utf-8")
    second = load_season_context(f)

    assert first.version != second.version
    assert first.text != second.text


def test_version_matches_for_identical_content_at_different_paths(tmp_path: Path) -> None:
    body = "identical content lives in two places\n"
    a_path = tmp_path / "a.md"
    b_path = tmp_path / "b.md"
    a_path.write_text(body, encoding="utf-8")
    b_path.write_text(body, encoding="utf-8")

    assert load_season_context(a_path).version == load_season_context(b_path).version


def test_missing_file_raises_clear_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    with pytest.raises(SeasonContextNotFoundError) as exc_info:
        load_season_context(missing)
    msg = str(exc_info.value)
    assert str(missing) in msg
    assert "season context" in msg.lower()


def test_missing_file_error_is_a_filenotfounderror() -> None:
    """Callers catching the stdlib base class should still catch our subclass."""
    assert issubclass(SeasonContextNotFoundError, FileNotFoundError)


def test_default_path_points_at_packaged_markdown() -> None:
    assert DEFAULT_PATH.name == "season_context.md"
    assert DEFAULT_PATH.exists()
