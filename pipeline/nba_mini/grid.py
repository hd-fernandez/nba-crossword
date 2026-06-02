"""Deterministic 5x5 mini-crossword grid fill.

Given a prioritized pool of "must-include" candidate answers (e.g. NBA-themed
words selected upstream from the day's discourse) plus a generic wordlist,
produce a valid 5x5 `Grid` (per `nba_mini.schema`) with every entry filled.

The seam:
- The LLM picks the *answer pool* (handled elsewhere). This module places
  those answers into a grid using rule-based constraint satisfaction. No LLM
  calls happen here. Determinism is guaranteed when caller passes a fixed
  `seed` and the wordlist is unchanged.

The algorithm:
1. Validate candidates (A-Z only, length 2..GRID_SIZE).
2. Pick a black-square template that matches the requested `black_squares`
   count. Templates are deterministically ordered by `seed`.
3. Pre-place candidates into compatible slots via depth-first enumeration.
4. Backtrack-fill remaining slots from the wordlist, picking the
   most-constrained slot first.
5. If a template cannot be filled, try the next template.
6. If all templates fail with the current candidate list, drop the
   *lowest-priority* candidate (last in the list) and retry. Log which
   candidates were dropped.
7. Cap total backtrack steps at `MAX_BACKTRACK_STEPS` to bound worst-case
   runtime (~2s on commodity hardware for v0).

Public surface:
- `fill_grid(candidate_answers, wordlist, *, black_squares=4, seed=0) -> Grid`
- `GridFillError` — raised when even the no-candidates fallback fails.

Tests live in `pipeline/tests/test_grid.py`.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Literal

from nba_mini.schema import GRID_SIZE, BlockCell, Cell, Direction, Grid, LetterCell

logger = logging.getLogger(__name__)

# Cap on total recursive descents during fill. ~2s on a modern laptop for v0.
# Bumped only if real puzzle inputs blow through it — first remediation
# should be a wider wordlist, not a higher cap.
MAX_BACKTRACK_STEPS = 10_000

# How many consecutive seeds to try in pursuit of a duplicate-free grid. A
# fully-crossed slot can rarely spell a word placed elsewhere; rather than
# reject that inside the backtracker (which starves the thin wordlist and fails
# almost every grid), we re-roll the seed a few times and prefer a clean fill,
# falling back to the first valid grid if none is clean. Small: duplicates are
# rare, and each extra seed is a full fill attempt.
DUPE_RETRY_SEEDS = 5

# Black-square templates, grouped by block count. Each template is a sorted
# tuple of (row, col) pairs. Templates are vetted to ensure every white cell
# belongs to one across run AND one down run, each of length >= 2.
#
# Adding a template? Run the slot-coverage assertion in the test suite
# (`test_all_templates_yield_valid_slot_coverage`) to confirm it's well-formed.
_TEMPLATES_BY_BLOCK_COUNT: dict[int, tuple[tuple[tuple[int, int], ...], ...]] = {
    2: (
        ((0, 4), (4, 0)),  # NE + SW corners (matches puzzles/example.json)
        ((0, 0), (4, 4)),  # NW + SE corners (mirror of the above)
    ),
    4: (
        ((0, 0), (0, 4), (4, 0), (4, 4)),  # all 4 corners — clean 3+5 fill
    ),
}

BlockSet = frozenset[tuple[int, int]]


@dataclass(frozen=True)
class Slot:
    """A single across or down run on the grid.

    `cells` is the in-order list of (row, col) cells the slot covers. The
    slot's length equals `len(cells)`.
    """

    start_row: int
    start_col: int
    direction: Direction
    cells: tuple[tuple[int, int], ...]

    @property
    def length(self) -> int:
        return len(self.cells)


@dataclass
class _FillState:
    """Mutable bookkeeping for one fill attempt against one template."""

    letters: list[list[str | None]]  # GRID_SIZE x GRID_SIZE; None = unfilled white
    blocks: BlockSet
    slots: tuple[Slot, ...]
    wordlist_by_length: dict[int, list[str]]
    # Per-length membership set of every word allowed to *complete* a slot:
    # the wordlist plus the run's candidates. Used to reject a fully-crossed
    # slot that happens to spell a non-word (e.g. crossing letters spelling
    # "CRBCA"). Without this guard the fill emits junk that the clue step then
    # fabricates fake NBA lore for. O(1) membership; built once per attempt.
    valid_by_length: dict[int, set[str]] = field(default_factory=dict)
    used_words: set[str] = field(default_factory=set)
    rng: random.Random = field(default_factory=random.Random)
    steps: int = 0


class GridFillError(RuntimeError):
    """No valid grid could be produced for the given inputs.

    Raised only when the fallback (no candidates, wordlist-only fill) also
    fails — i.e., the wordlist itself is too thin or no template fits.
    """


class InvalidCandidateError(ValueError):
    """A candidate answer contains characters outside A-Z or is the wrong length.

    The pipeline upstream should have normalized candidates already; this
    error indicates a contract violation, not a recoverable mismatch.
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fill_grid(
    candidate_answers: list[str],
    wordlist: list[str],
    *,
    black_squares: int = 4,
    seed: int = 0,
) -> Grid:
    """Produce a valid 5x5 `Grid` filled with the candidates and wordlist.

    Args:
        candidate_answers: Prioritized list of must-include answers. Earlier
            entries have higher priority; if the algorithm cannot fit them
            all, it drops from the tail. Each answer must be ALL-CAPS A-Z
            with length in [2, GRID_SIZE].
        wordlist: Pool of fallback fill words. Must include enough length-3
            and length-5 (and length-4 depending on template) entries to
            satisfy a typical fill. Passed through `nba_mini.wordlist` for
            normalization in the orchestrator.
        black_squares: Number of black squares in the chosen template.
            Defaults to 4. Only counts present in the template registry are
            valid — currently {2, 4}.
        seed: Determinism control. Same inputs + same seed -> same output.

    Returns:
        A `Grid` validated against `nba_mini.schema`.

    Raises:
        InvalidCandidateError: if any candidate fails the A-Z / length check.
        GridFillError: if no template can be filled, even after dropping
            every candidate.
        ValueError: if `black_squares` has no registered template.
    """
    _validate_candidates(candidate_answers)

    if black_squares not in _TEMPLATES_BY_BLOCK_COUNT:
        valid = sorted(_TEMPLATES_BY_BLOCK_COUNT)
        raise ValueError(
            f"no template registered for black_squares={black_squares}; "
            f"valid options: {valid}"
        )

    # Group wordlist by length once. Sort each bucket for deterministic
    # enumeration before any RNG shuffling.
    wordlist_by_length = _group_wordlist_by_length(wordlist)

    # Templates are tried in a seeded order. We rotate the registered tuple
    # by `seed % len(templates)` so the same seed always hits the same
    # primary template, but a stuck seed can fall through to the next one.
    templates = _TEMPLATES_BY_BLOCK_COUNT[black_squares]
    start = seed % len(templates)
    template_order = templates[start:] + templates[:start]

    # Seed-retry for duplicate avoidance: a fully-crossed slot can occasionally
    # spell a word already placed elsewhere (the "STY ×3" case). Rejecting that
    # inside the backtracker is too strict (it fails almost every grid against
    # the current wordlist), so instead we try a few seeds and prefer the first
    # duplicate-free grid. If none in the budget is clean, we return the first
    # valid grid anyway — a rare duplicate beats no puzzle. Determinism holds:
    # same inputs + same seed → same sequence of tried seeds → same result.
    first_grid: Grid | None = None
    for attempt in range(DUPE_RETRY_SEEDS):
        attempt_seed = seed + attempt
        grid = _fill_with_seed(
            candidate_answers,
            wordlist_by_length,
            template_order,
            black_squares,
            attempt_seed,
        )
        if grid is None:
            continue
        if first_grid is None:
            first_grid = grid
        if not _grid_has_duplicate_answers(grid):
            if attempt > 0:
                logger.info(
                    "fill_grid: seed %d had duplicate answers; used seed %d instead",
                    seed,
                    attempt_seed,
                )
            return grid

    if first_grid is not None:
        logger.warning(
            "fill_grid: no duplicate-free fill within %d seeds; shipping a grid "
            "with a repeated answer (seed=%d)",
            DUPE_RETRY_SEEDS,
            seed,
        )
        return first_grid

    # No template/seed produced any valid fill, even after dropping candidates.
    raise GridFillError(
        "no valid fill found: wordlist too thin for "
        f"black_squares={black_squares} (templates tried: {len(template_order)})"
    )


def _fill_with_seed(
    candidate_answers: list[str],
    wordlist_by_length: dict[int, list[str]],
    template_order: tuple[tuple[tuple[int, int], ...], ...],
    black_squares: int,
    seed: int,
) -> Grid | None:
    """One full fill attempt at a fixed seed, dropping candidates as needed.

    Returns the first valid grid found across the template order (progressively
    dropping the lowest-priority candidate when the full set can't be placed),
    or None if nothing fills even with no candidates.
    """
    candidates = list(candidate_answers)
    dropped: list[str] = []
    while True:
        for blocks in template_order:
            block_set: BlockSet = frozenset(blocks)
            slots = _compute_slots(block_set)
            grid = _attempt_fill(
                candidates=candidates,
                blocks=block_set,
                slots=slots,
                wordlist_by_length=wordlist_by_length,
                seed=seed,
            )
            if grid is not None:
                if dropped:
                    logger.info(
                        "fill_grid: dropped %d candidate(s) to find a fill: %s",
                        len(dropped),
                        dropped,
                    )
                return grid

        if not candidates:
            return None

        dropped_candidate = candidates.pop()
        dropped.append(dropped_candidate)
        logger.info(
            "fill_grid: candidate %r could not be placed; retrying without it",
            dropped_candidate,
        )


def _grid_has_duplicate_answers(grid: Grid) -> bool:
    """True if any answer (across or down) appears more than once in the grid."""
    letters = grid_to_letters(grid)
    words = [
        "".join(letters[r][c] or "" for r, c in slot.cells)
        for slot in slots_from_grid(grid)
    ]
    return len(words) != len(set(words))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_candidates(candidates: list[str]) -> None:
    for c in candidates:
        if not isinstance(c, str):
            raise InvalidCandidateError(
                f"candidate must be a string, got {type(c).__name__}: {c!r}"
            )
        if not c:
            raise InvalidCandidateError("candidate must be non-empty")
        if not (c.isascii() and c.isalpha() and c.isupper()):
            raise InvalidCandidateError(
                f"candidate {c!r} must be ALL-CAPS ASCII letters (A-Z) with "
                "no spaces, digits, or punctuation"
            )
        if not (2 <= len(c) <= GRID_SIZE):
            raise InvalidCandidateError(
                f"candidate {c!r} length {len(c)} outside [2, {GRID_SIZE}]"
            )


# ---------------------------------------------------------------------------
# Slot computation
# ---------------------------------------------------------------------------


def _compute_slots(blocks: BlockSet) -> tuple[Slot, ...]:
    """Find every across and down run of length >= 2 in the grid.

    A "run" is a maximal sequence of consecutive non-block cells in a row
    (across) or column (down). Length-1 runs are silently dropped — they
    can't carry an entry, and any template that produces them is malformed
    (caught in tests).
    """
    slots: list[Slot] = []

    # Across slots, row by row.
    for r in range(GRID_SIZE):
        c = 0
        while c < GRID_SIZE:
            if (r, c) in blocks:
                c += 1
                continue
            start_c = c
            cells: list[tuple[int, int]] = []
            while c < GRID_SIZE and (r, c) not in blocks:
                cells.append((r, c))
                c += 1
            if len(cells) >= 2:
                slots.append(
                    Slot(
                        start_row=r,
                        start_col=start_c,
                        direction="across",
                        cells=tuple(cells),
                    )
                )

    # Down slots, column by column.
    for c in range(GRID_SIZE):
        r = 0
        while r < GRID_SIZE:
            if (r, c) in blocks:
                r += 1
                continue
            start_r = r
            cells: list[tuple[int, int]] = []
            while r < GRID_SIZE and (r, c) not in blocks:
                cells.append((r, c))
                r += 1
            if len(cells) >= 2:
                slots.append(
                    Slot(
                        start_row=start_r,
                        start_col=c,
                        direction="down",
                        cells=tuple(cells),
                    )
                )

    return tuple(slots)


# ---------------------------------------------------------------------------
# Wordlist bucketing
# ---------------------------------------------------------------------------


def _group_wordlist_by_length(wordlist: list[str]) -> dict[int, list[str]]:
    """Pre-sort and bucket the wordlist by length for fast lookup."""
    buckets: dict[int, list[str]] = {}
    for word in wordlist:
        if not (word.isascii() and word.isalpha() and word.isupper()):
            # Defensive — the loader normalizes already, but skip junk if it
            # somehow got past.
            continue
        buckets.setdefault(len(word), []).append(word)
    for k in buckets:
        buckets[k] = sorted(set(buckets[k]))
    return buckets


# ---------------------------------------------------------------------------
# Fill attempt (one template, current candidate set)
# ---------------------------------------------------------------------------


def _attempt_fill(
    *,
    candidates: list[str],
    blocks: BlockSet,
    slots: tuple[Slot, ...],
    wordlist_by_length: dict[int, list[str]],
    seed: int,
) -> Grid | None:
    """Try to fill the given template with the given candidate set.

    Returns the validated `Grid` on success, or None if this template can't
    accommodate every candidate (in which case the caller drops a candidate
    or moves to the next template).
    """
    # A fully-crossed slot is only valid if it spells a candidate or a real
    # wordlist word. Build the per-length membership set once: wordlist ∪
    # candidates (candidates may legitimately be off-wordlist NBA terms).
    valid_by_length: dict[int, set[str]] = {
        length: set(words) for length, words in wordlist_by_length.items()
    }
    for cand in candidates:
        valid_by_length.setdefault(len(cand), set()).add(cand)

    state = _FillState(
        letters=[[None] * GRID_SIZE for _ in range(GRID_SIZE)],
        blocks=blocks,
        slots=slots,
        wordlist_by_length=wordlist_by_length,
        valid_by_length=valid_by_length,
        rng=random.Random(seed),
    )
    # Mark blocks in the letters matrix with a sentinel so we can render them
    # later without re-checking the block set. The `None` we already have
    # represents an unfilled white cell; we use the empty string "" as a
    # block sentinel since no real letter can be empty.
    for r, c in blocks:
        state.letters[r][c] = ""  # block sentinel

    # Place candidates first (depth-first across all assignments). On the
    # last candidate, the recursion calls into wordlist fill; if that fails,
    # the candidate placement keeps trying alternative slots.
    if not _place_candidates(state, candidates, candidate_index=0):
        return None

    return _build_grid(state)


def _place_candidates(
    state: _FillState, candidates: list[str], candidate_index: int
) -> bool:
    """Assign each candidate to a compatible slot, in order.

    Each candidate is tried against every slot whose length matches. A
    candidate is compatible if:
    - the slot is currently unassigned (no letters placed by a previous
      candidate in the recursion);
    - every cell in the slot either is empty or already holds the candidate's
      letter (i.e., crossings agree).

    On placement we write the candidate's letters into the grid; on
    backtrack we erase them.
    """
    if state.steps >= MAX_BACKTRACK_STEPS:
        return False

    if candidate_index >= len(candidates):
        # All candidates placed — now try to complete the grid from the
        # wordlist. If that fails, callers will backtrack the last
        # candidate's seat assignment.
        return _backtrack_fill(state)

    word = candidates[candidate_index]
    # Deterministic order: sort slots by (length, start_row, start_col, dir)
    # then shuffle with the seeded RNG so multiple seats are tried in a
    # repeatable but non-trivial order.
    eligible = [s for s in state.slots if s.length == len(word)]
    eligible_sorted = sorted(
        eligible,
        key=lambda s: (s.length, s.start_row, s.start_col, s.direction),
    )
    state.rng.shuffle(eligible_sorted)

    for slot in eligible_sorted:
        state.steps += 1
        if state.steps >= MAX_BACKTRACK_STEPS:
            return False

        # Snapshot which cells we wrote so we can roll back on failure.
        written: list[tuple[int, int]] = []
        ok = True
        # Refuse to place the same string twice — duplicates make a puzzle
        # cheap, and the schema's duplicate-start check would catch some
        # cases but not "same word in two slots."
        if word in state.used_words:
            continue
        for (r, c), letter in zip(slot.cells, word, strict=True):
            existing = state.letters[r][c]
            if existing is None:
                state.letters[r][c] = letter
                written.append((r, c))
            elif existing == letter:
                # crossing agrees — leave alone, don't add to rollback list.
                pass
            else:
                ok = False
                break

        if ok:
            state.used_words.add(word)
            if _place_candidates(state, candidates, candidate_index + 1):
                return True
            state.used_words.discard(word)

        # Roll back any letters we wrote in this attempt.
        for r, c in written:
            state.letters[r][c] = None

    return False


def _backtrack_fill(state: _FillState) -> bool:
    """Fill remaining slots from the wordlist, most-constrained first."""
    if state.steps >= MAX_BACKTRACK_STEPS:
        return False

    # Find the unfinished slot with the fewest matching wordlist candidates.
    target: Slot | None = None
    target_options: list[str] | None = None

    for slot in state.slots:
        pattern = _slot_pattern(state, slot)
        if "_" not in pattern:
            # Slot is fully filled by crossings. It's only valid if it spells
            # a real word or one of this run's candidates — otherwise the
            # crossings have spelled junk (e.g. "CRBCA"), which is a dead end:
            # backtrack so the caller tries a different word in a crossing
            # slot. (This is the guard that keeps non-words out of the grid.)
            #
            # NB: we intentionally do *not* reject a fully-crossed slot that
            # duplicates another answer here. A hard in-fill reject is
            # incompatible with this single-pass backtracker + current wordlist
            # — it failed ~100% of grids in testing. Duplicate answers are rare
            # and handled as a post-fill seed retry in ``fill_grid`` instead.
            if pattern not in state.valid_by_length.get(slot.length, ()):
                return False
            continue

        options = _matching_words(state.wordlist_by_length.get(slot.length, []), pattern)
        # Skip words already used.
        options = [w for w in options if w not in state.used_words]
        if not options:
            return False  # dead end — caller will backtrack
        if target_options is None or len(options) < len(target_options):
            target = slot
            target_options = options
            if len(options) == 1:
                break  # can't do better than 1; fail-fast pruning

    if target is None or target_options is None:
        # Every slot is filled — done.
        return True

    # Deterministic enumeration: shuffle options with the seeded RNG.
    # We keep the list sorted (it already is — wordlist is sorted) and
    # shuffle once per call for variety across recursion depths.
    options = list(target_options)
    state.rng.shuffle(options)

    for word in options:
        state.steps += 1
        if state.steps >= MAX_BACKTRACK_STEPS:
            return False

        written: list[tuple[int, int]] = []
        for (r, c), letter in zip(target.cells, word, strict=True):
            existing = state.letters[r][c]
            if existing is None:
                state.letters[r][c] = letter
                written.append((r, c))
            # If existing == letter, it's an agreed crossing (no-op).
            # If existing != letter we wouldn't have gotten this word from
            # `_matching_words`.

        state.used_words.add(word)
        if _backtrack_fill(state):
            return True
        state.used_words.discard(word)

        for r, c in written:
            state.letters[r][c] = None

    return False


# ---------------------------------------------------------------------------
# Pattern matching helpers
# ---------------------------------------------------------------------------


def _slot_pattern(state: _FillState, slot: Slot) -> str:
    """Render the slot's current state as a pattern string.

    Filled cells become their letter; unfilled cells become `_`. Example:
    a 5-letter slot with the second cell filled with 'A' renders as
    `"_A___"`.
    """
    out: list[str] = []
    for r, c in slot.cells:
        cell = state.letters[r][c]
        if cell is None:
            out.append("_")
        else:
            # We never call this on a block cell — slots don't include blocks.
            out.append(cell)
    return "".join(out)


def _matching_words(candidates: list[str], pattern: str) -> list[str]:
    """Filter `candidates` to those compatible with `pattern`.

    `pattern` characters: A-Z constrain that position; `_` means free.
    Assumes all candidates are the same length as the pattern; callers
    are expected to pre-bucket by length.
    """
    if "_" not in pattern:
        # Fast path: pattern is fully constrained — return at most one word.
        return [pattern] if pattern in candidates else []

    out: list[str] = []
    for word in candidates:
        match = True
        for w_ch, p_ch in zip(word, pattern, strict=True):
            if p_ch != "_" and p_ch != w_ch:
                match = False
                break
        if match:
            out.append(word)
    return out


# ---------------------------------------------------------------------------
# Final grid construction
# ---------------------------------------------------------------------------


def _build_grid(state: _FillState) -> Grid:
    """Convert the filled letter matrix into a validated `Grid` model."""
    cells: list[list[Cell]] = []
    for r in range(GRID_SIZE):
        row: list[Cell] = []
        for c in range(GRID_SIZE):
            value = state.letters[r][c]
            if value == "":
                row.append(BlockCell(block=True))
            elif value is None:
                # Should be impossible after a successful fill; defensive.
                raise GridFillError(
                    f"internal: cell ({r},{c}) is unfilled at grid build time"
                )
            else:
                row.append(LetterCell(answer=value))
        cells.append(row)
    return Grid(size=GRID_SIZE, cells=cells)


# ---------------------------------------------------------------------------
# Public helpers (used by callers and tests)
# ---------------------------------------------------------------------------


def slots_from_grid(grid: Grid) -> tuple[Slot, ...]:
    """Compute the slots present in a fully-built `Grid`.

    Useful for downstream code that needs to enumerate entries (e.g. clue
    generation in U7) without re-deriving the block set by hand.
    """
    blocks: set[tuple[int, int]] = set()
    for r, row in enumerate(grid.cells):
        for c, cell in enumerate(row):
            if isinstance(cell, BlockCell):
                blocks.add((r, c))
    return _compute_slots(frozenset(blocks))


def grid_to_letters(grid: Grid) -> list[list[str | None]]:
    """Render a `Grid` as a 5x5 letter matrix.

    Block cells become `None`. Useful for tests and for downstream code that
    wants the bare letter layout without the model wrapper.
    """
    out: list[list[str | None]] = []
    for row in grid.cells:
        out_row: list[str | None] = []
        for cell in row:
            if isinstance(cell, BlockCell):
                out_row.append(None)
            else:
                out_row.append(cell.answer)
        out.append(out_row)
    return out


# Re-exported sentinel literal for tests that want to assert on registered
# templates without poking at private names.
TemplateBlockCount = Literal[2, 4]


def registered_block_counts() -> tuple[int, ...]:
    """Sorted tuple of the block counts that have at least one template."""
    return tuple(sorted(_TEMPLATES_BY_BLOCK_COUNT))


def registered_templates(black_squares: int) -> tuple[BlockSet, ...]:
    """Templates registered for a given block count, as frozensets of (r,c)."""
    return tuple(frozenset(t) for t in _TEMPLATES_BY_BLOCK_COUNT[black_squares])
