"""Tests for the Bee puzzle schema."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from nba_mini.bee.schema import BeePuzzle, TierThresholds


def make_thresholds(**overrides: float) -> TierThresholds:
    """Default monotonically-ascending thresholds for tests; tweak as needed."""
    base = {
        "g_league_callup": 1.0,
        "rookie": 5.0,
        "sophomore": 12.0,
        "vet": 22.0,
        "all_star": 35.0,
        "champion": 50.0,
        "hall_of_famer": 70.0,
        "goat": 100.0,
    }
    base.update(overrides)
    return TierThresholds(**base)


def make_puzzle(**overrides) -> BeePuzzle:
    """A minimal valid Bee puzzle for tests; tweak any field via overrides.

    Board is L (center) + A B E N O R (outer). LEBRON uses 6 of the 7 letters
    (no A), so it's a valid name but not a pangram. ALEBRON is a synthetic
    7-letter string that uses every letter — the schema only checks
    structural rules, not corpus membership, so this is fine for fixtures.
    """
    base = dict(
        date="2026-05-22",
        league="nba",
        bee_number=1,
        center_letter="L",
        outer_letters=["A", "B", "E", "N", "O", "R"],
        valid_names=["LEBRON", "LOBO", "ALEBRON"],
        pangrams=["ALEBRON"],
        tier_thresholds=make_thresholds(),
        max_score=20,
        generated_at=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return BeePuzzle(**base)


# ---------------------------------------------------------------------------
# Tier thresholds
# ---------------------------------------------------------------------------


def test_thresholds_must_be_ascending() -> None:
    with pytest.raises(ValidationError, match="ascending"):
        make_thresholds(rookie=20.0, sophomore=10.0)


def test_top_tier_must_be_100() -> None:
    with pytest.raises(ValidationError, match="100"):
        make_thresholds(goat=95.0)


def test_thresholds_must_be_in_0_100_range() -> None:
    with pytest.raises(ValidationError):
        make_thresholds(rookie=-1.0)
    with pytest.raises(ValidationError):
        make_thresholds(vet=120.0)


def test_default_thresholds_round_trip() -> None:
    t = make_thresholds()
    re = TierThresholds.model_validate(t.model_dump())
    assert re == t


# ---------------------------------------------------------------------------
# Outer-letter shape
# ---------------------------------------------------------------------------


def test_outer_letters_must_have_six() -> None:
    with pytest.raises(ValidationError, match="6 entries"):
        make_puzzle(outer_letters=["A", "B", "E", "N", "O"])  # 5
    with pytest.raises(ValidationError, match="6 entries"):
        make_puzzle(outer_letters=["A", "B", "E", "N", "O", "R", "S"])  # 7


def test_outer_letters_must_be_uppercase_single_letters() -> None:
    with pytest.raises(ValidationError, match="A.{0,3}Z"):
        make_puzzle(outer_letters=["a", "B", "E", "N", "O", "R"])
    with pytest.raises(ValidationError):
        make_puzzle(outer_letters=["AB", "C", "D", "E", "F", "G"])


def test_outer_letters_cannot_contain_center() -> None:
    with pytest.raises(ValidationError, match="center_letter"):
        make_puzzle(center_letter="L", outer_letters=["L", "A", "B", "E", "N", "O"])


def test_outer_letters_must_be_distinct() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        make_puzzle(outer_letters=["A", "A", "B", "E", "N", "O"])


# ---------------------------------------------------------------------------
# Valid-names shape
# ---------------------------------------------------------------------------


def test_every_valid_name_uses_center_letter() -> None:
    # OBORE doesn't contain the center letter L.
    with pytest.raises(ValidationError, match="center letter"):
        make_puzzle(valid_names=["LEBRON", "OBORE"])


def test_every_valid_name_uses_only_board_letters() -> None:
    # LZONE uses L (center, ✓) but Z is not on the board.
    with pytest.raises(ValidationError, match="not on the board"):
        make_puzzle(valid_names=["LEBRON", "LZONE"])


def test_valid_names_must_be_uppercase_alpha() -> None:
    with pytest.raises(ValidationError, match="uppercase"):
        make_puzzle(valid_names=["LEBRON", "lebron"])


def test_empty_valid_names_entry_rejected() -> None:
    with pytest.raises(ValidationError, match="empty entry"):
        make_puzzle(valid_names=["LEBRON", ""])


def test_empty_valid_names_list_is_allowed() -> None:
    # Could happen on a board with no corpus matches; the generator's
    # job is to avoid this, but the schema doesn't forbid it outright.
    p = make_puzzle(valid_names=[], pangrams=[])
    assert p.valid_names == []


# ---------------------------------------------------------------------------
# Pangrams
# ---------------------------------------------------------------------------


def test_pangrams_must_be_in_valid_names() -> None:
    with pytest.raises(ValidationError, match="not in valid_names"):
        make_puzzle(pangrams=["LANEBOR"])  # uses all 7 but not in valid_names


def test_pangrams_must_use_all_seven_letters() -> None:
    # LOBO uses only L, O, B — not all 7. Listed as valid_names but isn't a pangram.
    with pytest.raises(ValidationError, match="all 7 letters"):
        make_puzzle(valid_names=["LEBRON", "LOBO"], pangrams=["LOBO"])


def test_no_pangrams_is_allowed() -> None:
    p = make_puzzle(pangrams=[])
    assert p.pangrams == []


# ---------------------------------------------------------------------------
# Date / metadata
# ---------------------------------------------------------------------------


def test_date_must_be_iso() -> None:
    with pytest.raises(ValidationError):
        make_puzzle(date="May 22 2026")


def test_bee_number_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_puzzle(bee_number=0)
    with pytest.raises(ValidationError):
        make_puzzle(bee_number=-1)


def test_max_score_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        make_puzzle(max_score=0)


def test_unknown_field_rejected() -> None:
    """Strict mode: typos surface at the boundary."""
    with pytest.raises(ValidationError):
        BeePuzzle(
            date="2026-05-22",
            league="nba",
            bee_number=1,
            center_letter="L",
            outer_letters=["A", "B", "E", "N", "O", "R"],
            valid_names=["LEBRON"],
            pangrams=["LEBRON"],
            tier_thresholds=make_thresholds(),
            max_score=20,
            generated_at=datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc),
            mystery_field="oops",  # type: ignore[call-arg]
        )


def test_league_must_be_known() -> None:
    with pytest.raises(ValidationError):
        make_puzzle(league="g_league")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_full_puzzle_round_trips_through_json() -> None:
    p = make_puzzle()
    redumped = BeePuzzle.model_validate_json(p.model_dump_json())
    assert redumped == p
