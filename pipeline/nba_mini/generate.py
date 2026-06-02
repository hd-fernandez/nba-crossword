"""End-to-end daily puzzle generator.

This is the U8 orchestrator from the v0 plan: a CLI entry point that runs the
whole pipeline for a single date and writes ``puzzles/<date>.json`` (or exits
cleanly on no-games days).

Order of operations:

    1. Load season context (U5).
    2. Fetch yesterday's NBA games (U4).
       - If ``NoGamesSignal``: log + exit 0; **no JSON written**. (R6 / AE3.)
    3. Fetch yesterday's r/nba discourse (U3).
    4. Pick a candidate-answer pool: prompt Sonnet (via the same ``ClueLLM``
       protocol the clue module uses) with the season context + digests, ask
       for ~7 short uppercase candidates, validate, drop invalid.
    5. Fill the grid (U6) using those candidates + the wordlist; daily seed =
       ``date.toordinal()`` for deterministic re-runs.
    6. Derive entries from the filled grid (slot scan order, NYT-style
       numbering: numbers run left-to-right, top-to-bottom; cells that start
       *any* entry get a number, and a single number is shared between an
       across and a down starting at the same cell).
    7. Generate clues (U7).
    8. Construct + validate the ``Puzzle`` (U2).
    9. Write ``puzzles/<date>.json`` (pretty, UTF-8) — unless ``--dry-run``,
       in which case dump to stdout.

Failure-loud philosophy: any typed dependency error (Reddit, nba.com, LLM,
grid-fill, schema validation) is allowed to bubble out of ``run_pipeline``;
``main`` catches them, logs a one-line message, and exits non-zero. We'd
rather miss a day than ship a half-baked puzzle — the cron will retry.

Dependency injection: ``run_pipeline`` takes a ``Deps`` container of
injectable callables. ``main`` builds the production ``Deps`` (real Reddit /
nba.com / Anthropic / wordlist); tests build ``Deps`` with stubs. This keeps
the orchestrator's flow testable without ever touching the network.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, Sequence
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from nba_mini.clues import (
    BEDROCK_DEFAULT_MODEL,
    DEFAULT_MODEL,
    AnthropicClueLLM,
    BedrockClueLLM,
    ClueLLM,
    ClueLLMOutageError,
    GenerationContext,
    PromptTemplateError,
    generate_clues,
)
from nba_mini.critic import build_critic_llm, critique_clues
from nba_mini.grid import (
    GridFillError,
    InvalidCandidateError,
    Slot,
    fill_grid,
    slots_from_grid,
)
from nba_mini.ingest.nba_stats import (
    GamesDigest,
    League,
    NBAStatsError,
    NoGamesSignal,
    fetch_recent_games,
)
from nba_mini.ingest.reddit import (
    RedditDigest,
    RedditIngestError,
    fetch_recent_discourse_rss,
)
from nba_mini.schema import GRID_SIZE, BlockCell, Entry, Grid, Puzzle
from nba_mini.season_context import (
    SeasonContext,
    SeasonContextNotFoundError,
    load_season_context,
)
from nba_mini.wordlist import WordlistNotFoundError, load_wordlist

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables / constants
# ---------------------------------------------------------------------------

CANDIDATE_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "candidate_answers.md"
"""Markdown prompt template for the candidate-answer LLM call."""

CANDIDATE_MIN_LEN = 2
CANDIDATE_MAX_LEN = GRID_SIZE
CANDIDATE_TARGET_COUNT = 7
"""How many candidates we *try* to keep from the LLM response. The plan calls
for ~7. The grid-fill algorithm gracefully drops surplus from the tail when
they don't fit."""

# US/Eastern offset for "yesterday" computation. Same simplification as the
# reddit ingest — the season window is always EDT (UTC-4); revisit only if a
# pipeline run ever straddles the November DST flip.
ET_OFFSET = timedelta(hours=-4)
# DST-aware Eastern zone. Used for the publish date so it matches the
# frontend's America/New_York computation (Intl.DateTimeFormat) year-round —
# the fixed ET_OFFSET above is an EDT-only approximation kept for the reddit
# windowing math, which only runs during the always-EDT season window.
EASTERN_TZ = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Deps container
# ---------------------------------------------------------------------------


# Type aliases for the injectable callables. These mirror the existing
# module-level functions so the production wiring is a no-op.
SeasonContextLoader = Callable[[], SeasonContext]
RedditFetcher = Callable[[date_cls], RedditDigest]
NBAStatsFetcher = Callable[[date_cls], "GamesDigest | NoGamesSignal"]
WordlistLoader = Callable[[], list[str]]

# Per-league subreddits for discourse ingest, in priority order (earlier subs
# win permalink-dedup ties). All are public RSS. The NBA set spans the main
# board, the discussion/analysis subs, and the meme/banter subs — the meme subs
# are title-heavy, which suits the RSS feed (titles only, no comment bodies).
_SUBREDDITS: dict[League, list[str]] = {
    "nba": [
        "nba",
        "nbadiscussion",
        "nbatalk",
        "nbaeastmemewar",
        "nbawestmemewar",
        "nbacirclejerk",
        "nbaconvo",
    ],
    "wnba": ["wnba"],
}

# How many days of recent games + discourse to pull into the pool. A full week
# (not just last night) so the puzzle reflects current events and — critically —
# has enough *distinct* storylines that clues don't all reach for the same one
# (the "thobe ×4" repetition problem).
#
# Why 7 and not more: Reddit's RSS is bucketed (day | week | month), and each
# bucket holds the *top* posts ranked over that span, not a continuous feed. The
# multi-day digest filters by exact timestamp afterward, so a bigger bucket only
# helps if it actually reaches back far enough. ``week`` is the last bucket that
# is *denser* than the window — every one of its (up to 100/sub) posts can fall
# inside 7 days. At >7 the ingest switches to ``month``, whose top-100 are ranked
# over ~31 days, so the timestamp filter discards most of them and yield *drops*
# (measured: 7d→160 posts, 10d→66). 7 is the real sweet spot, not an arbitrary
# cap. ``fetch_recent_discourse_rss`` logs a warning if asked for >7.
RECENCY_WINDOW_DAYS = 7


class ClueGenerator(Protocol):
    """Structural type for ``generate_clues`` and any test stand-in.

    The real ``generate_clues`` takes ``llm`` as a keyword-only argument; we
    mirror that here so the orchestrator's call site is type-safe.
    """

    def __call__(
        self,
        entries: list[Entry],
        context: GenerationContext,
        *,
        llm: ClueLLM | None = ...,
    ) -> list[Entry]: ...


@dataclass
class Deps:
    """Injectable dependencies for the orchestrator.

    Production callers use ``Deps.production(model=...)``; tests construct
    ``Deps(...)`` with stubs. Keeping every external seam here means the
    orchestrator body is just glue — easy to read, easy to fake.

    ``llm`` is the single LLM client used both by the candidate-pool prompt
    and (forwarded to) ``generate_clues``. Sharing one client matches the
    plan's intent: the pipeline talks to *one* Sonnet, not two.
    """

    season_context: SeasonContextLoader
    fetch_reddit: RedditFetcher
    fetch_games: NBAStatsFetcher
    load_wordlist: WordlistLoader
    llm: ClueLLM
    clue_generator: ClueGenerator = generate_clues
    model: str = DEFAULT_MODEL

    @staticmethod
    def production(
        *,
        model: str | None = None,
        backend: str | None = None,
        league: League = "nba",
    ) -> "Deps":
        """Build a ``Deps`` wired to the real Reddit / nba.com / LLM stacks.

        ``backend`` selects the LLM transport: ``"anthropic"`` (direct API,
        needs ``ANTHROPIC_API_KEY``) or ``"bedrock"`` (Claude on Amazon
        Bedrock, authed via the ambient AWS credential chain). When ``None``,
        falls back to the ``NBA_MINI_LLM_BACKEND`` env var, then ``"anthropic"``.

        ``league`` wires every league-specific seam to the same league: the
        season context, the subreddit feed, and the box-score endpoint's
        ``league_id``. ``fetch_games`` resolves the *most recent* slate at or
        before the date it's given, so the orchestrator gets the right
        look-back behavior for free.

        ``model`` defaults to the backend-appropriate default when ``None``:
        the bare Sonnet name for the direct API, or the region-prefixed
        inference-profile ID for Bedrock. The fetcher closures bind the
        per-date arguments inline so the ``Deps`` callables all share the same
        ``(date) -> result`` shape.
        """
        backend = (backend or os.environ.get("NBA_MINI_LLM_BACKEND") or "anthropic").lower()
        if backend == "bedrock":
            resolved_model = model or BEDROCK_DEFAULT_MODEL
            llm: ClueLLM = BedrockClueLLM(
                model=resolved_model,
                aws_region=os.environ.get("AWS_REGION"),
            )
        elif backend == "anthropic":
            resolved_model = model or DEFAULT_MODEL
            llm = AnthropicClueLLM(model=resolved_model)
        else:
            raise SystemExit(
                f"unknown LLM backend {backend!r}; expected 'anthropic' or 'bedrock'"
            )
        subreddits = _SUBREDDITS[league]

        # Clue generator with the quality gate wired in. The critic judges the
        # finished puzzle against the rubric and regenerates failing clues
        # (bounded rounds, ship-best-and-log). Disable with NBA_MINI_NO_CRITIC=1
        # for a cheaper/faster run (e.g. local debugging) — the daily cron keeps
        # it on by default. ``critique_clues`` fails open, so an LLM hiccup in
        # the critic never blocks the puzzle.
        critic_enabled = os.environ.get("NBA_MINI_NO_CRITIC", "").lower() not in (
            "1",
            "true",
            "yes",
        )

        # The critic needs its own client with a large token budget — judging a
        # whole puzzle returns a JSON array far bigger than the ~256 tokens that
        # suffice for one clue. Reusing the generation client truncates the
        # critic's response mid-JSON, which fails open and silently disables the
        # gate. Build a dedicated, self-contained critic instead.
        clue_critic = None
        if critic_enabled:
            critic_llm = build_critic_llm(
                backend=backend,
                model=resolved_model,
                aws_region=os.environ.get("AWS_REGION"),
            )

            def clue_critic(entries: list[Entry], context: GenerationContext):  # noqa: E731
                return critique_clues(entries, context, llm=critic_llm)

        def clue_generator(
            entries: list[Entry],
            context: GenerationContext,
            *,
            llm: ClueLLM | None = None,
        ) -> list[Entry]:
            return generate_clues(entries, context, llm=llm, critic=clue_critic)

        return Deps(
            season_context=lambda: load_season_context(league=league),
            fetch_reddit=lambda d: fetch_recent_discourse_rss(
                d, subreddits=subreddits, window_days=RECENCY_WINDOW_DAYS
            ),
            fetch_games=lambda d: fetch_recent_games(
                d, league=league, window_days=RECENCY_WINDOW_DAYS
            ),
            load_wordlist=lambda: load_wordlist(),
            llm=llm,
            clue_generator=clue_generator,
            model=resolved_model,
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_pipeline(
    target_date: date_cls,
    *,
    deps: Deps,
    puzzle_number: int = 1,
    league: str = "nba",
) -> Puzzle | None:
    """Run the full pipeline, publishing a puzzle dated ``target_date``.

    ``target_date`` is the *publish* date — the day this puzzle is served as
    "today's." The games it's built from are the league's **most recent
    slate at or before** ``target_date``, which ``deps.fetch_games`` resolves
    (it may walk back several days). The resulting ``GamesDigest.date`` is the
    *slate* date and is recorded on the puzzle as ``slate_date``; in the common
    case it's ``target_date - 1``, but on a Monday after a Saturday NBA slate
    it'll be the Saturday.

    Returns ``None`` when the league has no games anywhere in the lookback
    window — the caller treats this as the no-puzzle-today signal (R6 / AE3)
    and writes nothing.

    The ``league`` arg threads through to the ``Puzzle`` it constructs;
    season-context loading, ingest fetchers, and prompt assembly are
    handled by the injected ``Deps``, so the orchestrator itself stays
    league-agnostic.

    Raises one of the typed pipeline errors on hard failure (see below).
    The orchestrator does not catch any of them — ``main`` does, with a
    typed-error → exit-code mapping.
    """
    publish_iso = target_date.isoformat()
    logger.info("starting %s pipeline, publishing for %s", league, publish_iso)

    # 1. Season context.
    season = deps.season_context()
    logger.info("season context loaded: version=%s len=%d", season.version, len(season.text))

    # 2. Games: the most recent slate at or before the publish date. Cleanly
    #    short-circuit when the league hasn't played in the lookback window.
    games_result = deps.fetch_games(target_date)
    if isinstance(games_result, NoGamesSignal):
        logger.info("no %s games near %s; nothing to do", league, publish_iso)
        return None
    games_digest: GamesDigest = games_result
    slate_iso = games_digest.date
    logger.info(
        "games digest: %d game(s) from %s (slate)", len(games_digest.games), slate_iso
    )

    # 3. Reddit discourse over the recency window ending on the slate day. The
    #    fetcher's window is [d - window_days, d) in ET, so passing slate + 1
    #    covers the slate day and the prior days — matching the games window.
    slate_date = date_cls.fromisoformat(slate_iso)
    reddit_digest = deps.fetch_reddit(slate_date + timedelta(days=1))
    logger.info("reddit digest: %d post(s)", len(reddit_digest.posts))

    # 4. Candidate answer pool (LLM-assisted).
    candidates = pick_candidate_pool(
        season=season,
        reddit_digest=reddit_digest,
        games_digest=games_digest,
        llm=deps.llm,
    )
    logger.info("candidate pool (%d): %s", len(candidates), candidates)

    # 5. Fill the grid. Seed off the publish date so re-running the same day is
    #    deterministic (the file name is the publish date, so this matches).
    wordlist = deps.load_wordlist()
    seed = target_date.toordinal()
    grid = fill_grid(candidates, wordlist, seed=seed)

    # 6. Derive entries from the filled grid.
    entries_no_clues = entries_from_grid(grid)
    logger.info("derived %d entries from grid", len(entries_no_clues))

    # 7. Clue generation.
    ctx = GenerationContext(
        season_context_text=season.text,
        reddit_digest=reddit_digest,
        games_digest=games_digest,
        model=deps.model,
        seed=seed,
    )
    # The clue generator accepts an injectable LLM via kwarg in the real
    # implementation; we forward it explicitly so the same client is used.
    entries = deps.clue_generator(entries_no_clues, ctx, llm=deps.llm)

    # 8. Build + validate the puzzle. Pydantic enforces all invariants.
    puzzle = Puzzle(
        date=publish_iso,
        slate_date=slate_iso,
        league=league,  # type: ignore[arg-type]
        puzzle_number=puzzle_number,
        grid=grid,
        entries=entries,
        season_context_version=season.version,
        generated_at=datetime.now(tz=timezone.utc),
        model=deps.model,
    )
    return puzzle


# ---------------------------------------------------------------------------
# Candidate-answer pool
# ---------------------------------------------------------------------------


_CANDIDATE_RE = re.compile(r"^[A-Z]+$")

# How much of the (now much larger, body-rich) reddit pool to show the
# candidate-picker. With bodies extracted and a 100/sub feed, the pool is big
# enough that 10 posts left most storylines unseen; 24 gives the picker real
# breadth without blowing the prompt budget. Bodies are trimmed per-post.
_CANDIDATE_PROMPT_POSTS = 24
_CANDIDATE_PROMPT_BODY_CHARS = 400


def pick_candidate_pool(
    *,
    season: SeasonContext,
    reddit_digest: RedditDigest,
    games_digest: GamesDigest,
    llm: ClueLLM,
) -> list[str]:
    """Ask the LLM for a list of short uppercase NBA-flavored candidate answers.

    Returns the validated, deduplicated list (ordered by priority, highest
    first). Invalid entries (wrong length, non-letters, lowercase) are
    silently dropped per the prompt's contract. We do **not** raise on an
    empty result — fall back to an empty list and let ``fill_grid`` use the
    wordlist on its own (it has a no-candidates fallback path).

    Raises:
        ClueLLMOutageError: if the LLM call itself fails. We bubble out
            because the *next* call (clue generation) will fail too; better
            to abort the whole run than ship a fallback puzzle.
        PromptTemplateError: if the prompt markdown file is missing.
    """
    template = _load_candidate_prompt_template()
    prompt = template.format(
        season_context=season.text.strip(),
        reddit_digest=_format_reddit_for_prompt(reddit_digest),
        games_digest=_format_games_for_prompt(games_digest),
    )

    try:
        raw = llm.complete(prompt)
    except ClueLLMOutageError:
        raise
    except Exception as exc:  # noqa: BLE001 — coerce unknowns to the typed error
        raise ClueLLMOutageError(f"candidate-pool LLM call failed: {exc}") from exc

    parsed = _parse_candidate_response(raw)
    valid = _validate_and_normalize_candidates(parsed)
    # Trim to the target count, preserving priority order.
    return valid[:CANDIDATE_TARGET_COUNT]


def _load_candidate_prompt_template() -> str:
    try:
        return CANDIDATE_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptTemplateError(
            f"candidate-answer prompt not found at {CANDIDATE_PROMPT_PATH}"
        ) from exc


def _parse_candidate_response(raw: str) -> list[str]:
    """Extract the JSON array of strings from the model's response.

    Tolerant: strips surrounding code fences and prose before/after the
    array. If parsing fails entirely, returns ``[]`` so the orchestrator
    can carry on with a wordlist-only fill.
    """
    if not raw:
        return []

    text = raw.strip()
    # Peel a single layer of fenced code block if present.
    if text.startswith("```"):
        # Drop the first fence line (``` or ```json) and any trailing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # Try a direct parse first.
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        # Last-ditch: pull the substring between the first '[' and last ']'.
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            logger.warning("candidate-pool response was not parseable JSON: %r", raw[:200])
            return []
        try:
            loaded = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("candidate-pool response was not parseable JSON: %r", raw[:200])
            return []

    if not isinstance(loaded, list):
        logger.warning("candidate-pool response was not a list: %r", raw[:200])
        return []

    out: list[str] = []
    for item in loaded:
        if isinstance(item, str):
            out.append(item)
    return out


def _validate_and_normalize_candidates(items: Sequence[str]) -> list[str]:
    """Uppercase + filter to ``A-Z`` only with length in [MIN, MAX]; dedupe."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        word = raw.strip().upper()
        if not _CANDIDATE_RE.match(word):
            continue
        if not (CANDIDATE_MIN_LEN <= len(word) <= CANDIDATE_MAX_LEN):
            continue
        if word in seen:
            continue
        seen.add(word)
        out.append(word)
    return out


def _format_reddit_for_prompt(digest: RedditDigest) -> str:
    """Compact reddit digest serialization for the candidate-pool prompt."""
    if not digest.posts:
        return "(no posts)"
    lines: list[str] = []
    for post in digest.posts[:_CANDIDATE_PROMPT_POSTS]:
        flair = f" [{post.flair}]" if post.flair else ""
        lines.append(f"- {post.title}{flair} (score {post.score})")
        if post.body:
            # The self-text body is where the real storyline detail lives —
            # exactly the "current events" signal candidate-picking should see.
            body = post.body
            if len(body) > _CANDIDATE_PROMPT_BODY_CHARS:
                body = body[:_CANDIDATE_PROMPT_BODY_CHARS].rsplit(" ", 1)[0] + "…"
            lines.append(f"  > {body}")
        for c in post.top_comments[:3]:
            lines.append(f"  - {c}")
    return "\n".join(lines)


def _format_games_for_prompt(digest: GamesDigest) -> str:
    """Compact games digest serialization for the candidate-pool prompt."""
    if not digest.games:
        return "(no games)"
    lines: list[str] = []
    for game in digest.games:
        events = f" [{', '.join(game.notable_events)}]" if game.notable_events else ""
        lines.append(f"- {game.score}{events}")
        if game.series_context:
            lines.append(f"  ({game.series_context})")
        for perf in game.top_performers:
            lines.append(f"  - {perf.player} ({perf.team}): {perf.statline}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entries from grid
# ---------------------------------------------------------------------------


def entries_from_grid(grid: Grid) -> list[Entry]:
    """Build the schema-shaped entry list from a filled ``Grid``.

    Numbering convention (matches NYT mini and the example puzzle):
      - Scan cells in row-major order.
      - A cell gets a number iff it starts at least one entry (across or
        down). "Starts" = is a letter cell whose preceding cell in that
        direction is a block or off-grid, *and* whose run in that direction
        has length >= 2.
      - When a single cell starts both an across and a down entry, both
        share the same number (e.g. ``1A`` and ``1D`` at row 0 col 0).

    Each entry's ``clue`` is set to a placeholder ``"?"`` and ``voice`` to
    ``"factual"``; ``generate_clues`` overwrites both. We use ``"?"`` rather
    than ``""`` because ``Entry.clue`` has ``min_length=1`` — pydantic would
    reject an empty placeholder.
    """
    slots = slots_from_grid(grid)
    # Index slots by (start_row, start_col) for quick lookup during numbering.
    starts: dict[tuple[int, int], list[Slot]] = {}
    for slot in slots:
        starts.setdefault((slot.start_row, slot.start_col), []).append(slot)

    entries: list[Entry] = []
    next_number = 1
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            here = starts.get((r, c))
            if not here:
                continue
            number = next_number
            next_number += 1
            # Sort for stability: across before down at the same cell.
            for slot in sorted(here, key=lambda s: 0 if s.direction == "across" else 1):
                answer = _slot_answer(grid, slot)
                direction_letter = "A" if slot.direction == "across" else "D"
                entries.append(
                    Entry(
                        id=f"{number}{direction_letter}",
                        direction=slot.direction,
                        row=slot.start_row,
                        col=slot.start_col,
                        answer=answer,
                        clue="?",  # placeholder; generate_clues overwrites.
                        voice="factual",  # placeholder; generate_clues overwrites.
                    )
                )
    return entries


def _slot_answer(grid: Grid, slot: Slot) -> str:
    """Read the letters of ``slot`` out of ``grid``. Block cells would be a bug."""
    chars: list[str] = []
    for r, c in slot.cells:
        cell = grid.cells[r][c]
        if isinstance(cell, BlockCell):
            # Slots are computed from the block set; they should never include
            # a block cell. Fail loud if the invariant breaks.
            raise RuntimeError(
                f"slot at ({slot.start_row},{slot.start_col},{slot.direction}) "
                f"includes a block cell at ({r},{c}) — invariant violation"
            )
        chars.append(cell.answer)
    return "".join(chars)


# ---------------------------------------------------------------------------
# Date / output helpers
# ---------------------------------------------------------------------------


def yesterday_in_eastern(now: datetime | None = None) -> date_cls:
    """Yesterday in US/Eastern.

    Mirrors the simplification used by the reddit ingest: ET is treated as a
    fixed UTC-4 (EDT) offset because the season window is always EDT. Good
    enough for v0. Retained for the reddit windowing math and back-compat.
    """
    instant = now if now is not None else datetime.now(tz=timezone.utc)
    et = instant + ET_OFFSET
    return (et - timedelta(days=1)).date()


def today_in_eastern(now: datetime | None = None) -> date_cls:
    """Default *publish* date: today in US/Eastern.

    The puzzle is published for today; the pipeline then looks back for the
    league's most recent slate, so we no longer default the date to yesterday.

    Uses DST-aware ``America/New_York`` (not the fixed ET_OFFSET) so the
    publish date agrees with the frontend's ``todayInEastern`` — which also
    uses ``America/New_York`` — around local midnight in EST months. A
    one-hour offset error there would otherwise let the pipeline publish under
    a date the app isn't yet asking for.
    """
    instant = now if now is not None else datetime.now(tz=timezone.utc)
    return instant.astimezone(EASTERN_TZ).date()


def puzzle_path_for(date_str: str, out_dir: Path) -> Path:
    """Return the JSON file path for a given date inside ``out_dir``."""
    return out_dir / f"{date_str}.json"


_DATED_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def next_puzzle_number(out_dir: Path, target_iso: str) -> int:
    """Compute the puzzle number to assign to ``target_iso``.

    The number is the count of existing dated puzzle files at or before the
    target date, plus 1. This makes the assignment stable across re-runs of
    the same date (an existing file counts as "itself", not as "another"),
    and stable across backfills of older dates (a backfill of yesterday gets
    the right number even if today's puzzle is already on disk).

    The "example.json" fixture is intentionally excluded because it isn't a
    real published puzzle.
    """
    if not out_dir.exists():
        return 1
    earlier_or_equal = 0
    target_already_present = False
    for p in out_dir.iterdir():
        if not _DATED_FILENAME_RE.match(p.name):
            continue
        date_part = p.stem
        if date_part == target_iso:
            target_already_present = True
            continue
        if date_part < target_iso:
            earlier_or_equal += 1
    # Index from 1: first ever puzzle is #1.
    base = earlier_or_equal + 1
    # If the target file already exists (regenerate / --force path), assigning
    # `base` keeps the number stable. If it doesn't yet exist, `base` is also
    # correct (we're appending after `earlier_or_equal` existing puzzles).
    _ = target_already_present  # kept for readability; logic identical either way
    return base


def write_puzzle_json(puzzle: Puzzle, path: Path) -> None:
    """Serialize a ``Puzzle`` to ``path`` as pretty-printed UTF-8 JSON.

    We round-trip through ``model_dump_json`` so the datetime / enum
    serialization matches pydantic's canonical form, then re-pretty-print
    with ``json.dumps(indent=2)`` so the on-disk file is human-friendly.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.loads(puzzle.model_dump_json())
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m nba_mini.generate",
        description="Generate the daily NBA mini crossword for a given date.",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help=(
            "Publish date (ISO YYYY-MM-DD): the day this puzzle is served as "
            "today's. Defaults to today in US/Eastern. The pipeline looks back "
            "from here for the league's most recent slate."
        ),
    )
    parser.add_argument(
        "--league",
        type=str,
        choices=("nba", "wnba"),
        default="nba",
        help=(
            "League to generate for. Selects the season context, subreddit, "
            "and box-score endpoint. Also the default output subdirectory "
            "(puzzles/<league>/). Default: nba."
        ),
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help=(
            "Root directory to write into. The <league> subdir is always "
            "appended, so --out ../puzzles writes ../puzzles/<league>/<date>.json. "
            "Defaults to the repo-root puzzles/ (e.g. puzzles/nba/)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip writing the file; print the puzzle JSON to stdout.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing puzzle file at the target path.",
    )
    parser.add_argument(
        "--backend",
        type=str,
        choices=("anthropic", "bedrock"),
        default=None,
        help=(
            "LLM transport. 'anthropic' uses the direct API (ANTHROPIC_API_KEY); "
            "'bedrock' uses Claude on Amazon Bedrock (ambient AWS credentials). "
            "Defaults to $NBA_MINI_LLM_BACKEND, then 'anthropic'."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "Model ID to record on the puzzle. Defaults to the backend default "
            f"({DEFAULT_MODEL} for anthropic, {BEDROCK_DEFAULT_MODEL} for bedrock)."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose logging (DEBUG level).",
    )
    return parser.parse_args(argv)


def _resolve_date(arg: str | None) -> date_cls:
    if arg is None:
        return today_in_eastern()
    try:
        return date_cls.fromisoformat(arg)
    except ValueError as exc:
        raise SystemExit(f"invalid --date {arg!r}: expected YYYY-MM-DD ({exc})") from exc


def main(argv: Sequence[str] | None = None, *, deps: Deps | None = None) -> int:
    """CLI entry point. Returns the process exit code.

    The ``deps`` kwarg is for tests — production callers leave it None and we
    build ``Deps.production()`` lazily so importing this module doesn't try
    to construct an Anthropic client.
    """
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    target_date = _resolve_date(args.date)
    iso = target_date.isoformat()
    league: League = args.league
    # Output dir: <root>/<league>/. The root defaults to "puzzles/"; an
    # explicit --out replaces the root but the league subdir is always
    # appended, so `--out ../puzzles` writes ../puzzles/<league>/ — matching
    # the per-league layout the frontend serves and the cron expects.
    out_root = Path(args.out) if args.out else Path("puzzles")
    out_dir = out_root / league
    target_path = puzzle_path_for(iso, out_dir)

    # Idempotency: if the puzzle is already on disk and the user didn't ask
    # to force, exit clean. The cron job is therefore safe to re-run.
    if target_path.exists() and not args.force and not args.dry_run:
        logger.info(
            "puzzle for %s already exists at %s; pass --force to regenerate",
            iso,
            target_path,
        )
        return 0

    if deps is None:
        deps = Deps.production(model=args.model, backend=args.backend, league=league)

    puzzle_num = next_puzzle_number(out_dir, iso)
    try:
        puzzle = run_pipeline(
            target_date, deps=deps, puzzle_number=puzzle_num, league=league
        )
    except RedditIngestError as exc:
        logger.error("reddit ingest failed for %s: %s", iso, exc)
        return 1
    except NBAStatsError as exc:
        logger.error("nba.com ingest failed for %s: %s", iso, exc)
        return 1
    except ClueLLMOutageError as exc:
        logger.error("LLM call failed for %s: %s", iso, exc)
        return 1
    except (GridFillError, InvalidCandidateError) as exc:
        logger.error("grid fill failed for %s: %s", iso, exc)
        return 1
    except (SeasonContextNotFoundError, WordlistNotFoundError, PromptTemplateError) as exc:
        logger.error("missing required pipeline asset for %s: %s", iso, exc)
        return 1
    except ValidationError as exc:
        # This means we built a Puzzle that doesn't satisfy the schema —
        # structurally broken, not a content issue. Worth shouting about.
        logger.error("assembled puzzle for %s failed schema validation: %s", iso, exc)
        return 1

    if puzzle is None:
        # No-games day. R6 / AE3.
        return 0

    if args.dry_run:
        # Pretty-print to stdout so a human can eyeball it.
        payload = json.loads(puzzle.model_dump_json())
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0

    write_puzzle_json(puzzle, target_path)
    logger.info("wrote puzzle to %s", target_path)
    return 0


if __name__ == "__main__":  # pragma: no cover — covered indirectly by tests
    raise SystemExit(main())
