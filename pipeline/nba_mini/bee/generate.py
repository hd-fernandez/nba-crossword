"""Daily Bee puzzle generator.

Given a per-league names corpus and a daily seed, pick a (center letter,
six outer letters) board such that:

  1. At least 1 pangram exists in the corpus for that board (plays a
     7-letter name using all 7 letters)
  2. Total valid corpus names fall in [TARGET_MIN, TARGET_MAX]
  3. The center letter is a "good middle weight" (B/C/D/F/G/H/J/K/L/M/
     N/P/R/S/T/W) — Q/X/Z are too restrictive; A/E/I/O are too permissive

The algorithm is deterministic given the seed. It enumerates pangram
candidates (corpus names of length 7 with 7 distinct letters), uses each
as a board template, picks a center letter from the pangram, and counts
how many other corpus names fit. The first board hitting the target
window wins.

If no board hits the target after exhausting candidates, we return the
best-scoring board we saw (closest to the target midpoint) rather than
failing — better to ship a slightly-off Bee than no Bee.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from nba_mini.bee.corpus import CorpusEntry, League, load_corpus, names_only
from nba_mini.bee.schema import BeePuzzle, TierThresholds

logger = logging.getLogger(__name__)

# Target window for valid-name count per puzzle. Brainstorm: 12-25.
TARGET_MIN = 12
TARGET_MAX = 25
TARGET_MID = (TARGET_MIN + TARGET_MAX) // 2

# Center-letter "good middle weight" set. Excludes vowels (too permissive)
# and Q/X/Z (too restrictive).
GOOD_CENTERS = frozenset("BCDFGHJKLMNPRSTW")

# Hard ceiling on attempts so a pathological corpus can't hang the daily run.
MAX_BOARD_ATTEMPTS = 5000

DEFAULT_TIER_THRESHOLDS = TierThresholds(
    g_league_callup=1.0,
    rookie=5.0,
    sophomore=12.0,
    vet=22.0,
    all_star=35.0,
    champion=50.0,
    hall_of_famer=70.0,
    goat=100.0,
)


class BeeGenerationError(RuntimeError):
    """Raised when the generator cannot produce *any* viable board."""


@dataclass(frozen=True)
class _BoardCandidate:
    """A scored (center, outer) board, ready to become a BeePuzzle."""

    center: str
    outer: tuple[str, ...]  # length 6, sorted, distinct, no center
    valid_names: tuple[str, ...]
    pangrams: tuple[str, ...]

    @property
    def board(self) -> frozenset[str]:
        return frozenset((self.center, *self.outer))


def _names_with_seven_distinct_letters(names: Iterable[str]) -> list[tuple[str, frozenset[str]]]:
    """Filter to names that could anchor a board (exactly 7 distinct letters).

    Returns (name, letter_set) pairs. The letter_set IS the board if we
    pick this name as the pangram template.
    """
    out: list[tuple[str, frozenset[str]]] = []
    for n in names:
        letters = frozenset(n)
        if len(letters) == 7:
            out.append((n, letters))
    return out


def _count_valid(
    names: Iterable[str],
    board: frozenset[str],
    center: str,
) -> tuple[list[str], list[str]]:
    """Return (valid_names, pangrams) for a candidate board.

    A name is valid iff:
      - center letter is present
      - every letter in the name is on the board

    A pangram additionally uses every letter on the board.
    """
    valid: list[str] = []
    pangrams: list[str] = []
    for n in names:
        if center not in n:
            continue
        used = set(n)
        if not used <= board:
            continue
        valid.append(n)
        if used == board:
            pangrams.append(n)
    return valid, pangrams


def _score_candidate(valid_count: int, pangram_count: int) -> int:
    """Lower is better. 0 = exactly inside the target window, hits its midpoint.

    We strongly prefer boards inside [TARGET_MIN, TARGET_MAX]; outside the
    window we penalize the distance from the nearest edge so we still
    pick the closest miss as a fallback.
    """
    if pangram_count == 0:
        return 10_000  # disqualified-but-not-yet-rejected
    if TARGET_MIN <= valid_count <= TARGET_MAX:
        return abs(valid_count - TARGET_MID)
    if valid_count < TARGET_MIN:
        return 100 + (TARGET_MIN - valid_count)
    return 100 + (valid_count - TARGET_MAX)


def _candidate_boards(
    corpus_names: list[str],
    rng: random.Random,
) -> Iterable[_BoardCandidate]:
    """Yield candidate boards in shuffled order.

    Algorithm: every name with exactly 7 distinct letters is a potential
    pangram template. We shuffle those, then for each one try every center
    letter from that name that's in the GOOD_CENTERS set.
    """
    pangram_seeds = _names_with_seven_distinct_letters(corpus_names)
    rng.shuffle(pangram_seeds)
    attempts = 0
    for pangram, board_letters in pangram_seeds:
        # The center letter has to be one of the 7 board letters AND in
        # the good-centers set. Try each in turn; the rng order makes this
        # deterministic within a seed.
        candidate_centers = [c for c in board_letters if c in GOOD_CENTERS]
        rng.shuffle(candidate_centers)
        for center in candidate_centers:
            outer = tuple(sorted(board_letters - {center}))
            valid, pangrams = _count_valid(corpus_names, board_letters, center)
            attempts += 1
            if attempts > MAX_BOARD_ATTEMPTS:
                return
            yield _BoardCandidate(
                center=center,
                outer=outer,
                valid_names=tuple(sorted(valid)),
                pangrams=tuple(sorted(pangrams)),
            )


def generate_bee(
    league: League,
    *,
    date_str: str,
    bee_number: int,
    seed: int,
    corpus: list[CorpusEntry] | None = None,
    tier_thresholds: TierThresholds = DEFAULT_TIER_THRESHOLDS,
) -> BeePuzzle:
    """Generate a Bee puzzle for ``league`` on ``date_str``.

    Args:
        league: Which league's corpus to draw from.
        date_str: ISO YYYY-MM-DD; baked into the puzzle.
        bee_number: Sequential count since launch for this league.
        seed: Daily seed for determinism. Same seed + corpus + thresholds
            always produces the same puzzle.
        corpus: Pre-loaded corpus. If None, loads from disk.
        tier_thresholds: Override the default 8-tier ladder.

    Returns:
        A schema-validated ``BeePuzzle``.

    Raises:
        BeeGenerationError: when no candidate board has ≥1 pangram, or no
            board exists at all (e.g., corpus has no 7-distinct-letter
            names).
    """
    if corpus is None:
        corpus = load_corpus(league)

    name_set = names_only(corpus)
    corpus_names = sorted(name_set)  # sorted for determinism inside RNG shuffles
    rng = random.Random(seed)

    # Collect all candidate boards (capped) so we can pick deterministically
    # from the score-tied set. Without this, the *first* visited candidate
    # always wins ties — and with a sparse corpus most ties happen at the
    # fallback score, so the seed barely steers the outcome.
    all_candidates: list[_BoardCandidate] = []
    for candidate in _candidate_boards(corpus_names, rng):
        score = _score_candidate(len(candidate.valid_names), len(candidate.pangrams))
        all_candidates.append(candidate)
        # Early-out only when we hit a target-window board with a pangram —
        # that's the gold case.
        if score < 100 and candidate.pangrams:
            best = candidate
            best_score = score
            logger.info(
                "bee[%s] picked board center=%s outer=%s valid=%d pangrams=%d (in target)",
                league, candidate.center, "".join(candidate.outer),
                len(candidate.valid_names), len(candidate.pangrams),
            )
            break
    else:
        # No target-window hit — pick from the score-tied set deterministically.
        # All_candidates is in seed-shuffled order (rng was used to shuffle
        # both the pangram seeds and the per-seed center letters).
        if not all_candidates:
            best = None
            best_score = 10_000_000
        else:
            scored = [
                (
                    _score_candidate(len(c.valid_names), len(c.pangrams)),
                    c,
                )
                for c in all_candidates
            ]
            scored.sort(key=lambda x: x[0])
            min_score = scored[0][0]
            tied = [c for s, c in scored if s == min_score]
            # Tied set is already in seed-shuffled order from `_candidate_boards`,
            # so picking the first is deterministic per seed AND varies by seed.
            best = tied[0]
            best_score = min_score

    if best is None:
        raise BeeGenerationError(
            f"no candidate boards for league={league}; "
            "corpus likely has no names with 7 distinct letters"
        )
    if not best.pangrams:
        raise BeeGenerationError(
            f"no board with ≥1 pangram for league={league}; "
            f"best had valid={len(best.valid_names)} pangrams=0"
        )

    if best_score >= 100:
        logger.warning(
            "bee[%s] no board hit target window; shipping closest "
            "(valid=%d, target=[%d, %d])",
            league, len(best.valid_names), TARGET_MIN, TARGET_MAX,
        )

    max_score = sum(
        _name_points(n, n in set(best.pangrams)) for n in best.valid_names
    )

    return BeePuzzle(
        date=date_str,
        league=league,
        bee_number=bee_number,
        center_letter=best.center,
        outer_letters=list(best.outer),
        valid_names=list(best.valid_names),
        pangrams=list(best.pangrams),
        tier_thresholds=tier_thresholds,
        max_score=max_score,
        generated_at=datetime.now(tz=timezone.utc),
    )


def _name_points(name: str, is_pangram: bool) -> int:
    """Standard NYT Bee scoring; mirrored on the TS side in lib/bee.ts.

    4 letters = 1 point. Each additional letter adds +1. Pangrams get a +7
    bonus on top of the length score.
    """
    n = len(name)
    if n < 4:
        return 0
    base = 1 if n == 4 else n
    return base + 7 if is_pangram else base
