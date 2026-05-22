"""Canonical Bee puzzle JSON schema. Mirrored on the TypeScript side in
web/lib/bee.ts.

A Bee puzzle is one center letter, six outer letters, plus the answer key
(the list of corpus names that can be formed from those 7 letters with the
center letter required). Tier thresholds are baked into the JSON so the
frontend can render the ladder without consulting the corpus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

League = Literal["nba", "wnba", "combined"]

# Tier thresholds are stored as % of max_score (0–100). The frontend
# multiplies by max_score to get the integer-points threshold for each tier.
TIER_KEYS = (
    "g_league_callup",
    "rookie",
    "sophomore",
    "vet",
    "all_star",
    "champion",
    "hall_of_famer",
    "goat",
)
TierKey = Literal[
    "g_league_callup",
    "rookie",
    "sophomore",
    "vet",
    "all_star",
    "champion",
    "hall_of_famer",
    "goat",
]


class TierThresholds(BaseModel):
    """Percent-of-max-score thresholds for each tier (0–100, ascending)."""

    model_config = ConfigDict(extra="forbid")

    g_league_callup: float = Field(ge=0, le=100)
    rookie: float = Field(ge=0, le=100)
    sophomore: float = Field(ge=0, le=100)
    vet: float = Field(ge=0, le=100)
    all_star: float = Field(ge=0, le=100)
    champion: float = Field(ge=0, le=100)
    hall_of_famer: float = Field(ge=0, le=100)
    goat: float = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ascending(self) -> "TierThresholds":
        values = [getattr(self, k) for k in TIER_KEYS]
        for i in range(1, len(values)):
            if values[i] < values[i - 1]:
                raise ValueError(
                    f"tier thresholds must be ascending; "
                    f"{TIER_KEYS[i]}({values[i]}) < {TIER_KEYS[i - 1]}({values[i - 1]})"
                )
        if values[-1] != 100:
            raise ValueError(
                f"top tier (goat) must be 100 (saw {values[-1]}); "
                "the GOAT threshold is by definition every name found"
            )
        return self


class BeePuzzle(BaseModel):
    """One day's Bee, one league.

    Storage layout: ``puzzles/<league>/bee/<date>.json`` (parallel to the
    crossword's ``puzzles/<league>/<date>.json``).
    """

    model_config = ConfigDict(extra="forbid")

    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    league: League
    bee_number: int = Field(ge=1)
    """Sequential count since launch, independent per league."""

    center_letter: Annotated[str, Field(pattern=r"^[A-Z]$")]
    """The required letter — every valid name must use it."""

    outer_letters: list[str]
    """Six uppercase A–Z letters, distinct from the center and from each other."""

    valid_names: list[str]
    """Every corpus name formable from the 7 letters using the center.

    Stored as the uppercase NAME (matches against the corpus's NAME field).
    The frontend looks up display strings via the corpus on render — we
    intentionally don't ship display per-puzzle to keep the JSON compact.
    """

    pangrams: list[str]
    """Subset of valid_names that use ALL 7 letters. Worth the +7 bonus."""

    tier_thresholds: TierThresholds
    """Percent-of-max-score thresholds for the 8 reachable tiers."""

    max_score: int = Field(ge=1)
    """Score earned by finding every name. Used by the frontend to map %
    thresholds to absolute points."""

    generated_at: datetime

    @model_validator(mode="after")
    def _outer_letters_well_formed(self) -> "BeePuzzle":
        if len(self.outer_letters) != 6:
            raise ValueError(
                f"outer_letters must have 6 entries; got {len(self.outer_letters)}"
            )
        for ch in self.outer_letters:
            if not (isinstance(ch, str) and len(ch) == 1 and "A" <= ch <= "Z"):
                raise ValueError(
                    f"outer_letters entries must be uppercase A–Z; got {ch!r}"
                )
        if self.center_letter in self.outer_letters:
            raise ValueError(
                f"center_letter {self.center_letter!r} cannot also appear in outer_letters"
            )
        if len(set(self.outer_letters)) != 6:
            raise ValueError("outer_letters must be distinct (no duplicates)")
        return self

    @model_validator(mode="after")
    def _names_use_only_board_letters(self) -> "BeePuzzle":
        board = {self.center_letter, *self.outer_letters}
        for name in self.valid_names:
            if not name:
                raise ValueError("valid_names contains an empty entry")
            if not name.isupper() or not name.isalpha():
                raise ValueError(f"valid_names entry {name!r} is not uppercase A–Z")
            if self.center_letter not in name:
                raise ValueError(
                    f"valid_names entry {name!r} does not use the center letter "
                    f"{self.center_letter!r}"
                )
            for ch in name:
                if ch not in board:
                    raise ValueError(
                        f"valid_names entry {name!r} uses letter {ch!r} "
                        f"not on the board"
                    )
        return self

    @model_validator(mode="after")
    def _pangrams_subset_of_valid(self) -> "BeePuzzle":
        valid_set = set(self.valid_names)
        board = {self.center_letter, *self.outer_letters}
        for p in self.pangrams:
            if p not in valid_set:
                raise ValueError(
                    f"pangram {p!r} is not in valid_names"
                )
            if set(p) != board:
                raise ValueError(
                    f"pangram {p!r} does not use all 7 letters of the board"
                )
        return self
