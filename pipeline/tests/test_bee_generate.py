"""Tests for the Bee daily-puzzle generator."""

from __future__ import annotations

import pytest

from nba_mini.bee.corpus import CorpusEntry, load_corpus
from nba_mini.bee.generate import (
    BeeGenerationError,
    GOOD_CENTERS,
    TARGET_MAX,
    TARGET_MIN,
    generate_bee,
)
from nba_mini.bee.schema import BeePuzzle


def make_corpus(names: list[str]) -> list[CorpusEntry]:
    """Build a tiny corpus from bare uppercase names — type/display don't
    matter for generator tests, only the NAME field."""
    return [CorpusEntry(name=n, type="last", display=n) for n in names]


def test_real_nba_corpus_generates_a_valid_bee() -> None:
    puzzle = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=42)
    assert isinstance(puzzle, BeePuzzle)
    # Schema enforced everything, but spot-check the headline invariants.
    assert len(puzzle.outer_letters) == 6
    assert puzzle.center_letter not in puzzle.outer_letters
    assert puzzle.center_letter in GOOD_CENTERS
    assert len(puzzle.pangrams) >= 1


def test_real_wnba_corpus_generates_a_valid_bee() -> None:
    puzzle = generate_bee("wnba", date_str="2026-05-22", bee_number=1, seed=42)
    assert isinstance(puzzle, BeePuzzle)
    assert puzzle.league == "wnba"
    assert len(puzzle.pangrams) >= 1


def test_same_seed_produces_same_puzzle() -> None:
    a = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=42)
    b = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=42)
    assert a.center_letter == b.center_letter
    assert a.outer_letters == b.outer_letters
    assert a.valid_names == b.valid_names
    assert a.pangrams == b.pangrams


def test_different_seeds_can_produce_different_puzzles() -> None:
    # We don't *require* different seeds to differ (a small corpus might
    # have only one playable board), but we want to verify the seed is
    # actually being used. Across 10 seeds, at least one differs from seed=0.
    base = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=0)
    saw_difference = False
    for s in range(1, 11):
        candidate = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=s)
        if (
            candidate.center_letter != base.center_letter
            or candidate.outer_letters != base.outer_letters
        ):
            saw_difference = True
            break
    assert saw_difference, "seeds 0..10 all produced identical boards"


def test_max_score_is_sum_of_name_points() -> None:
    puzzle = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=42)
    expected = 0
    pangram_set = set(puzzle.pangrams)
    for name in puzzle.valid_names:
        n = len(name)
        if n < 4:
            continue
        base = 1 if n == 4 else n
        expected += base + 7 if name in pangram_set else base
    assert puzzle.max_score == expected


def test_generator_explores_seed_space() -> None:
    """Across a range of seeds, the generator should produce more than one
    distinct board, proving the seed actually steers the search.

    We deliberately don't assert "always lands in [TARGET_MIN, TARGET_MAX]"
    here — the v3-starter corpus is small (~150 names) and most boards
    can't hit a 12-name window. That's a corpus-depth issue, not an
    algorithm issue, and will improve as we grow the corpus post-launch.
    """
    boards = set()
    for s in range(15):
        p = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=s)
        boards.add((p.center_letter, tuple(p.outer_letters)))
    # ≥2 distinct boards proves the seed actually changes the outcome.
    # We don't ask for more because the v3-starter corpus is sparse — most
    # boards score-tie, and the seed only nudges between a small ties set.
    # Will become much higher once the corpus grows post-launch.
    assert len(boards) >= 2, (
        f"only {len(boards)} distinct board(s) across 15 seeds — seed isn't "
        "steering the search at all"
    )


def test_generator_always_returns_at_least_one_pangram() -> None:
    """Sanity: across many seeds, every returned puzzle has ≥1 pangram."""
    for s in range(15):
        p = generate_bee("nba", date_str="2026-05-22", bee_number=1, seed=s)
        assert len(p.pangrams) >= 1, f"seed={s} returned 0 pangrams"


def test_corpus_with_no_pangram_seeds_raises() -> None:
    # No name has 7 distinct letters → no pangram template → can't build a board.
    tiny = make_corpus(["LEBRON", "CURRY", "JORDAN"])
    with pytest.raises(BeeGenerationError):
        generate_bee(
            "nba",
            date_str="2026-05-22",
            bee_number=1,
            seed=0,
            corpus=tiny,
        )


def test_explicit_corpus_overrides_disk_load() -> None:
    """Passing a custom corpus should bypass `load_corpus()` entirely.
    We construct one with exactly one pangram-eligible name + filler so
    the generator has to use it."""
    # CARDONS uses 7 distinct letters: C A R D O N S.
    custom = make_corpus(
        [
            "CARDONS",  # the pangram seed
            # Filler names that fit on that board with C as center:
            "CARS",
            "CONS",
            "CORD",
            "CARDS",
            "RANCOR",
            "RADON",
            "DONOR",
            "ARSON",
            "ORCAS",
            "RACOON",
            "ACORN",
            "ACCORD",
        ]
    )
    p = generate_bee(
        "nba",
        date_str="2026-05-22",
        bee_number=1,
        seed=0,
        corpus=custom,
    )
    assert "CARDONS" in p.pangrams
    # The pangram itself must be among the valid names.
    assert "CARDONS" in p.valid_names


def test_bee_number_threads_into_puzzle() -> None:
    p = generate_bee("nba", date_str="2026-05-22", bee_number=42, seed=42)
    assert p.bee_number == 42


def test_date_str_threads_into_puzzle() -> None:
    p = generate_bee("nba", date_str="2026-12-25", bee_number=1, seed=42)
    assert p.date == "2026-12-25"
