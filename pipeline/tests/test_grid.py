"""Tests for the 5x5 grid fill algorithm.

Coverage targets (from the v0 plan, U6):
- Happy path: trivial candidate pool produces a valid grid.
- Determinism: same seed -> same grid, different seed may differ.
- Graceful relaxation: over-constrained candidates get dropped from the tail.
- Tiny-wordlist failure: raises GridFillError, doesn't infinite-loop.
- Validation: non-letter candidates are rejected with a clear error.
- Integration: the produced grid plus synthetic entries validates as a Puzzle.

We also include a structural sanity check on the registered black-square
templates: every template must produce a slot covering for every white cell
in both directions, with min entry length 2.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from nba_mini.grid import (
    GridFillError,
    InvalidCandidateError,
    Slot,
    _compute_slots,
    fill_grid,
    grid_to_letters,
    registered_block_counts,
    registered_templates,
    slots_from_grid,
)
from nba_mini.schema import GRID_SIZE, BlockCell, Entry, Grid, LetterCell, Puzzle
from nba_mini.wordlist import load_wordlist


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_wordlist() -> list[str]:
    """The packaged v0 wordlist. Module-scoped because file I/O is heavy."""
    return load_wordlist()


# A deliberately tiny wordlist used to exercise the failure path. It only
# contains a couple of length-3 words and nothing else, so no template can
# possibly be filled.
_TINY_WORDLIST = ["CAT", "DOG"]


# ---------------------------------------------------------------------------
# Template structural integrity
# ---------------------------------------------------------------------------


def test_registered_block_counts_are_known() -> None:
    counts = registered_block_counts()
    assert counts, "expected at least one template registered"
    for c in counts:
        assert c >= 0


def test_every_template_has_full_slot_coverage() -> None:
    """Every white cell must be in exactly one across slot and one down slot.

    This is the structural invariant the fill algorithm assumes. A template
    that violates it would produce 1-letter or uncovered cells, which would
    fail the Puzzle validator downstream.
    """
    for count in registered_block_counts():
        for blocks in registered_templates(count):
            slots = _compute_slots(blocks)

            across_cells: dict[tuple[int, int], int] = {}
            down_cells: dict[tuple[int, int], int] = {}
            for slot in slots:
                assert slot.length >= 2, (
                    f"template {sorted(blocks)} produced a length<2 slot: {slot}"
                )
                bucket = across_cells if slot.direction == "across" else down_cells
                for cell in slot.cells:
                    bucket[cell] = bucket.get(cell, 0) + 1

            for r in range(GRID_SIZE):
                for c in range(GRID_SIZE):
                    if (r, c) in blocks:
                        assert (r, c) not in across_cells
                        assert (r, c) not in down_cells
                    else:
                        assert across_cells.get((r, c)) == 1, (
                            f"cell ({r},{c}) not covered by exactly one across slot "
                            f"in template {sorted(blocks)}"
                        )
                        assert down_cells.get((r, c)) == 1, (
                            f"cell ({r},{c}) not covered by exactly one down slot "
                            f"in template {sorted(blocks)}"
                        )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_fill_grid_with_no_candidates_uses_only_wordlist(real_wordlist: list[str]) -> None:
    """Sanity: the algorithm can fill a grid from the wordlist alone."""
    grid = fill_grid([], real_wordlist, seed=0)
    _assert_grid_is_well_formed(grid, expected_block_count=4)


def test_fill_grid_places_a_compatible_candidate(real_wordlist: list[str]) -> None:
    """A length-3 candidate that the wordlist already knows about is placed."""
    grid = fill_grid(["AREA"], real_wordlist, seed=1, black_squares=2)
    letters = grid_to_letters(grid)
    placements = _find_word_placements(letters, "AREA")
    assert placements, "expected AREA to appear somewhere on the grid"


def test_fill_grid_default_black_squares_is_4(real_wordlist: list[str]) -> None:
    grid = fill_grid([], real_wordlist, seed=2)
    block_count = sum(1 for row in grid.cells for c in row if isinstance(c, BlockCell))
    assert block_count == 4


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_seed_produces_same_grid(real_wordlist: list[str]) -> None:
    a = fill_grid([], real_wordlist, seed=42)
    b = fill_grid([], real_wordlist, seed=42)
    assert grid_to_letters(a) == grid_to_letters(b)


def test_same_seed_with_candidates_is_deterministic(real_wordlist: list[str]) -> None:
    candidates = ["AREA", "ERA"]
    a = fill_grid(candidates, real_wordlist, seed=7, black_squares=2)
    b = fill_grid(candidates, real_wordlist, seed=7, black_squares=2)
    assert grid_to_letters(a) == grid_to_letters(b)


def test_different_seeds_can_produce_different_grids(real_wordlist: list[str]) -> None:
    """Soft check: at least one pair of seeds in a small range diverges.

    We don't require *every* seed pair to differ — different seeds can land
    on the same fill — but the algorithm shouldn't be a constant function.
    """
    fills = {
        tuple(tuple(row) for row in grid_to_letters(fill_grid([], real_wordlist, seed=s)))
        for s in range(8)
    }
    assert len(fills) > 1, "expected at least two distinct fills across seeds 0..7"


# ---------------------------------------------------------------------------
# Graceful relaxation
# ---------------------------------------------------------------------------


def test_overconstrained_candidates_still_yield_a_grid(
    real_wordlist: list[str],
) -> None:
    """Many unrelated 5-letter candidates: even if some get dropped, return a grid.

    The exact dropping path depends on which candidates happen to cross
    cleanly. We assert only the strong invariant: the function returns a
    well-formed grid, never raises. This covers the spec scenario "an
    over-constrained input gracefully drops candidates and still returns
    a valid grid (or raises a clear typed error if absolutely nothing
    works)."
    """
    candidates = ["XXXAA", "YYYBB", "ZZZCC"]
    # Three nonsensical 5-letter "words". They almost certainly won't
    # cross with each other or with anything in the wordlist. The
    # algorithm must drop them all and fill from the wordlist alone.
    grid = fill_grid(candidates, real_wordlist, seed=3, black_squares=2)
    _assert_grid_is_well_formed(grid, expected_block_count=2)


def test_dropped_candidates_are_logged(
    real_wordlist: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """When candidates can't be placed, the algorithm logs which were dropped."""
    # Hopelessly incompatible candidates — guaranteed to drop everything.
    candidates = ["XXXAA", "YYYBB", "ZZZCC"]
    with caplog.at_level(logging.INFO, logger="nba_mini.grid"):
        fill_grid(candidates, real_wordlist, seed=5, black_squares=2)

    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "could not be placed" in log_text
    # The summary message should also fire when at least one candidate was dropped.
    assert "dropped" in log_text or "to find a fill" in log_text


# ---------------------------------------------------------------------------
# Tiny wordlist failure
# ---------------------------------------------------------------------------


def test_tiny_wordlist_raises_grid_fill_error() -> None:
    """A wordlist of just two 3-letter words can't fill any registered template.

    The algorithm must raise GridFillError, not loop forever. The cap on
    backtrack steps protects us either way.
    """
    with pytest.raises(GridFillError):
        fill_grid([], _TINY_WORDLIST, seed=0)


def test_empty_wordlist_with_no_candidates_raises() -> None:
    with pytest.raises(GridFillError):
        fill_grid([], [], seed=0)


# ---------------------------------------------------------------------------
# Candidate validation
# ---------------------------------------------------------------------------


def test_candidate_with_digits_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError, match="ALL-CAPS"):
        fill_grid(["LBJ23"], real_wordlist, seed=0)


def test_candidate_with_lowercase_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError, match="ALL-CAPS"):
        fill_grid(["lebron"], real_wordlist, seed=0)


def test_candidate_with_space_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError, match="ALL-CAPS"):
        fill_grid(["MAGIC JOHNSON"], real_wordlist, seed=0)


def test_empty_candidate_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError):
        fill_grid([""], real_wordlist, seed=0)


def test_overlong_candidate_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError, match="length"):
        fill_grid(["LONGWORDS"], real_wordlist, seed=0)


def test_one_letter_candidate_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(InvalidCandidateError, match="length"):
        fill_grid(["A"], real_wordlist, seed=0)


def test_invalid_black_squares_count_is_rejected(real_wordlist: list[str]) -> None:
    with pytest.raises(ValueError, match="no template"):
        fill_grid([], real_wordlist, seed=0, black_squares=99)


# ---------------------------------------------------------------------------
# Integration with the schema
# ---------------------------------------------------------------------------


def test_filled_grid_round_trips_through_puzzle_schema(real_wordlist: list[str]) -> None:
    """Build a synthetic Puzzle around the filled grid; assert it validates."""
    grid = fill_grid([], real_wordlist, seed=11)
    letters = grid_to_letters(grid)

    entries: list[Entry] = []
    for i, slot in enumerate(slots_from_grid(grid)):
        answer = "".join(letters[r][c] or "" for r, c in slot.cells)
        entries.append(
            Entry(
                id=f"{i + 1}{slot.direction[0].upper()}",
                direction=slot.direction,
                row=slot.start_row,
                col=slot.start_col,
                answer=answer,
                clue="placeholder clue for schema integration test.",
                voice="factual",
            )
        )

    puzzle = Puzzle(
        date="2026-05-17",
        puzzle_number=1,
        grid=grid,
        entries=entries,
        season_context_version="test0001",
        generated_at=datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc),
        model="test-fixture",
    )

    # Round-trip through JSON to make sure pydantic agrees end-to-end.
    redumped = puzzle.model_dump_json()
    assert Puzzle.model_validate_json(redumped) is not None


def test_filled_grid_has_correct_dimensions(real_wordlist: list[str]) -> None:
    grid = fill_grid([], real_wordlist, seed=4)
    assert grid.size == GRID_SIZE
    assert len(grid.cells) == GRID_SIZE
    for row in grid.cells:
        assert len(row) == GRID_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_grid_is_well_formed(grid: Grid, *, expected_block_count: int | None = None) -> None:
    """Cheap structural check shared by several tests."""
    assert grid.size == GRID_SIZE
    assert len(grid.cells) == GRID_SIZE
    block_count = 0
    for row in grid.cells:
        assert len(row) == GRID_SIZE
        for cell in row:
            if isinstance(cell, BlockCell):
                block_count += 1
            else:
                assert isinstance(cell, LetterCell)
                assert cell.answer.isascii()
                assert cell.answer.isupper()
                assert len(cell.answer) == 1
    if expected_block_count is not None:
        assert block_count == expected_block_count

    # Every letter cell must belong to one across slot and one down slot of
    # length >= 2 — this is what the Puzzle validator requires downstream.
    slots = slots_from_grid(grid)
    across = {cell for s in slots if s.direction == "across" for cell in s.cells}
    down = {cell for s in slots if s.direction == "down" for cell in s.cells}
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if isinstance(grid.cells[r][c], LetterCell):
                assert (r, c) in across, f"({r},{c}) missing from any across slot"
                assert (r, c) in down, f"({r},{c}) missing from any down slot"


def _find_word_placements(
    letters: list[list[str | None]], word: str
) -> list[tuple[int, int, str]]:
    """Return (row, col, direction) for each occurrence of `word` in the grid."""
    placements: list[tuple[int, int, str]] = []
    n = len(word)

    # Across.
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE - n + 1):
            if all(letters[r][c + i] == word[i] for i in range(n)):
                placements.append((r, c, "across"))
    # Down.
    for c in range(GRID_SIZE):
        for r in range(GRID_SIZE - n + 1):
            if all(letters[r + i][c] == word[i] for i in range(n)):
                placements.append((r, c, "down"))
    return placements


def test_slot_dataclass_length_matches_cells() -> None:
    s = Slot(
        start_row=0,
        start_col=0,
        direction="across",
        cells=((0, 0), (0, 1), (0, 2)),
    )
    assert s.length == 3
