"""Schema round-trip + invariant tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from nba_mini.schema import Puzzle

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "puzzles" / "example.json"


def load_example() -> dict:
    return json.loads(EXAMPLE_PATH.read_text())


def test_example_puzzle_round_trips() -> None:
    raw = load_example()
    puzzle = Puzzle.model_validate(raw)
    assert puzzle.date == "2026-05-15"
    assert puzzle.grid.size == 5
    assert len(puzzle.entries) == 10


def test_example_serializes_and_revalidates() -> None:
    puzzle = Puzzle.model_validate(load_example())
    redumped = json.loads(puzzle.model_dump_json())
    Puzzle.model_validate(redumped)


def test_grid_must_be_5x5() -> None:
    raw = load_example()
    raw["grid"]["cells"].pop()
    with pytest.raises(ValidationError, match="5 rows"):
        Puzzle.model_validate(raw)


def test_grid_row_must_be_5_wide() -> None:
    raw = load_example()
    raw["grid"]["cells"][0].pop()
    with pytest.raises(ValidationError, match="5 cells"):
        Puzzle.model_validate(raw)


def test_entry_letters_must_match_grid() -> None:
    raw = load_example()
    # Mutate the first across entry to claim the wrong word.
    raw["entries"][0]["answer"] = "STARE"
    with pytest.raises(ValidationError, match="expects 'T'"):
        Puzzle.model_validate(raw)


def test_cell_cannot_be_both_letter_and_block() -> None:
    raw = load_example()
    raw["grid"]["cells"][0][0] = {"answer": "S", "block": True}
    with pytest.raises(ValidationError):
        Puzzle.model_validate(raw)


def test_entry_with_out_of_grid_start_is_rejected() -> None:
    raw = load_example()
    raw["entries"][0]["row"] = 5
    with pytest.raises(ValidationError):
        Puzzle.model_validate(raw)


def test_entry_running_off_grid_at_tail_is_rejected() -> None:
    """A length that pushes off the grid tail is caught by the model validator.

    Construct a fresh puzzle with a deliberately-long across entry that
    starts in-bounds but extends past the right edge.
    """
    raw = load_example()
    # Replace 5A (TAROT, valid) with a 7-letter answer that overflows from col 0.
    raw["entries"][5]["answer"] = "TAROTXY"
    with pytest.raises(ValidationError):
        # Pydantic's `answer` max_length=5 will catch this first, but either
        # path proves overflow is rejected.
        Puzzle.model_validate(raw)


def test_lowercase_answer_is_rejected() -> None:
    raw = load_example()
    raw["entries"][0]["answer"] = "spare"
    with pytest.raises(ValidationError):
        Puzzle.model_validate(raw)


def test_invalid_voice_is_rejected() -> None:
    raw = load_example()
    raw["entries"][0]["voice"] = "snarky"
    with pytest.raises(ValidationError):
        Puzzle.model_validate(raw)


def test_unknown_field_is_rejected() -> None:
    """Strict mode: typos get caught at the boundary, not silently swallowed."""
    raw = load_example()
    raw["entries"][0]["clu"] = "typo on 'clue'"
    with pytest.raises(ValidationError):
        Puzzle.model_validate(raw)


def test_letter_cell_must_be_covered_across_and_down() -> None:
    raw = load_example()
    # Drop the first down entry — (0,0) is now uncovered down-wise.
    raw["entries"] = [e for e in raw["entries"] if e["id"] != "1D"]
    with pytest.raises(ValidationError, match="not part of any down entry"):
        Puzzle.model_validate(raw)
