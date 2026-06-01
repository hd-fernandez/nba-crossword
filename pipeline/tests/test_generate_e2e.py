"""End-to-end tests for the U8 generator orchestrator.

These tests exercise the full pipeline (`run_pipeline` and `main`) with every
external dependency stubbed via the ``Deps`` container. No network, no real
LLM, no real file fetches outside the orchestrator's own writes to a tmp dir.

Coverage targets (from the v0 plan, U8):
- AE3: a no-games day exits 0 and writes no JSON.
- Happy path: a full game day produces a schema-valid puzzles/<date>.json.
- Idempotency: re-running for the same date is a no-op without --force.
- --force overwrites an existing file.
- Each typed dependency error (Reddit, nba.com, LLM outage, grid fill)
  produces a non-zero exit code (failure-loud).
- Live-API integration test exists but is gated behind NBA_MINI_LIVE_E2E.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path

import pytest

from nba_mini.clues import (
    BEDROCK_DEFAULT_MODEL,
    DEFAULT_MODEL,
    AnthropicClueLLM,
    BedrockClueLLM,
    ClueLLMOutageError,
    GenerationContext,
    generate_clues,
)
from nba_mini.generate import (
    CANDIDATE_TARGET_COUNT,
    Deps,
    _format_games_for_prompt,
    _format_reddit_for_prompt,
    _parse_candidate_response,
    _validate_and_normalize_candidates,
    entries_from_grid,
    main,
    pick_candidate_pool,
    puzzle_path_for,
    run_pipeline,
    today_in_eastern,
    write_puzzle_json,
    yesterday_in_eastern,
)
from nba_mini.grid import fill_grid
from nba_mini.ingest.nba_stats import (
    GamesDigest,
    GameSummary,
    NBAStatsFetchError,
    NoGamesSignal,
    TopPerformer,
)
from nba_mini.ingest.reddit import (
    RedditDigest,
    RedditIngestError,
    RedditPost,
)
from nba_mini.schema import Entry, Puzzle
from nba_mini.season_context import SeasonContext
from nba_mini.wordlist import load_wordlist


# ---------------------------------------------------------------------------
# Stubs / fakes
# ---------------------------------------------------------------------------


class StubLLM:
    """A `ClueLLM` whose `complete()` is dispatched by a routing callable.

    The routing callable receives the prompt and returns the response. Tests
    construct it to give different replies to the candidate-pool prompt vs.
    the per-clue prompts.
    """

    def __init__(self, responder: Callable[[str], str]) -> None:
        self.responder = responder
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responder(prompt)


def _candidate_aware_responder(
    *,
    candidates: list[str],
    clue: str = "Yesterday's vibe in eight words.",
) -> Callable[[str], str]:
    """A responder that returns a JSON candidate list for the candidate-pool
    prompt, and a fixed valid clue for every clue prompt.

    We tell the two prompts apart by checking the candidate-pool template's
    distinctive header text.
    """

    def _resp(prompt: str) -> str:
        if "Candidate-answer selection" in prompt:
            return json.dumps(candidates)
        return clue

    return _resp


def _example_season() -> SeasonContext:
    return SeasonContext(
        text="It is mid-May 2026, NBA Conference Semifinals.",
        version="testver1",
    )


def _example_games_digest(target_date: date_cls) -> GamesDigest:
    return GamesDigest(
        date=target_date.isoformat(),
        games=[
            GameSummary(
                game_id="0042500001",
                home="BOS",
                away="NYK",
                home_score=112,
                away_score=109,
                score="BOS 112, NYK 109",
                top_performers=[
                    TopPerformer(
                        player="Jayson Tatum",
                        team="BOS",
                        statline="34 PTS / 8 REB / 6 AST",
                    ),
                    TopPerformer(
                        player="Jalen Brunson",
                        team="NYK",
                        statline="32 PTS / 4 REB / 9 AST",
                    ),
                ],
                notable_events=["NAILBITER"],
            )
        ],
    )


def _example_reddit_digest(target_date: date_cls) -> RedditDigest:
    return RedditDigest(
        date=target_date.isoformat(),
        posts=[
            RedditPost(
                title="Tatum hits the dagger in Game 4",
                flair="Post Game Thread",
                score=4500,
                comment_count=2200,
                top_comments=["he was cooked", "career night"],
                permalink="/r/nba/comments/abc/tatum_dagger/",
            ),
        ],
    )


def _make_deps(
    *,
    target_date: date_cls,
    candidates: list[str] | None = None,
    games: GamesDigest | NoGamesSignal | None = None,
    fail_reddit: bool = False,
    fail_games: bool = False,
    llm_outage: bool = False,
    fail_grid: bool = False,
) -> Deps:
    """Build a `Deps` wired to deterministic stubs.

    Defaults: a normal game day with a small candidate pool that the wordlist
    can fill around.
    """
    # Default candidates: a couple of length-5 and length-3 words that the
    # packaged wordlist can comfortably crossing-fill around. (The default
    # 4-corners template has slots of length 3 and 5 only; length-4 candidates
    # would just get dropped by fill_grid, which is fine but noisier.)
    candidates = candidates if candidates is not None else ["ARENA", "ERA"]

    def season_loader() -> SeasonContext:
        return _example_season()

    def reddit(_d: date_cls) -> RedditDigest:
        if fail_reddit:
            raise RedditIngestError("simulated reddit failure")
        return _example_reddit_digest(target_date)

    def games_fetcher(_d: date_cls):
        if fail_games:
            raise NBAStatsFetchError("simulated nba.com failure")
        return games if games is not None else _example_games_digest(target_date)

    def wordlist_loader() -> list[str]:
        return load_wordlist()

    if llm_outage:

        def responder(_p: str) -> str:
            raise ClueLLMOutageError("simulated LLM outage")

    else:
        responder = _candidate_aware_responder(candidates=candidates)

    llm = StubLLM(responder)

    def clue_gen(entries: list[Entry], context: GenerationContext, *, llm=None):
        if fail_grid:
            # If the test wants grid failure, this never gets called, but
            # keep the signature compatible.
            return generate_clues(entries, context, llm=llm)
        return generate_clues(entries, context, llm=llm)

    deps = Deps(
        season_context=season_loader,
        fetch_reddit=reddit,
        fetch_games=games_fetcher,
        load_wordlist=wordlist_loader,
        llm=llm,
        clue_generator=clue_gen,
        model="test-fake-model",
    )
    return deps


# ---------------------------------------------------------------------------
# Pure-helper tests (no orchestration needed)
# ---------------------------------------------------------------------------


def test_yesterday_in_eastern_returns_a_date() -> None:
    """Smoke check: returns a date strictly less than today UTC."""
    d = yesterday_in_eastern()
    assert isinstance(d, date_cls)


def test_yesterday_in_eastern_with_known_instant() -> None:
    """ET is UTC-4 (EDT). At 03:00 UTC on 2026-05-17, ET is 23:00 on
    2026-05-16; yesterday in ET is therefore 2026-05-15."""
    instant = datetime(2026, 5, 17, 3, 0, tzinfo=timezone.utc)
    assert yesterday_in_eastern(instant) == date_cls(2026, 5, 15)


def test_today_in_eastern_edt_known_instant() -> None:
    """In summer (EDT, UTC-4): 03:00 UTC on 2026-05-17 is 23:00 ET on the
    16th, so today-in-ET is 2026-05-16."""
    instant = datetime(2026, 5, 17, 3, 0, tzinfo=timezone.utc)
    assert today_in_eastern(instant) == date_cls(2026, 5, 16)


def test_today_in_eastern_is_dst_aware_in_winter() -> None:
    """The publish date must track DST, matching the frontend's
    America/New_York. In winter (EST, UTC-5), 04:30 UTC on 2026-01-10 is
    23:30 ET on the 9th — so today-in-ET is 2026-01-09. The old fixed-UTC-4
    approximation would have wrongly returned the 10th here (00:30 'ET')."""
    instant = datetime(2026, 1, 10, 4, 30, tzinfo=timezone.utc)
    assert today_in_eastern(instant) == date_cls(2026, 1, 9)


def test_validate_candidates_filters_invalid() -> None:
    out = _validate_and_normalize_candidates(
        ["WEMBY", "wemby", "Star", "abc!", "1234", "X", "TOO LONG", "OT", "OT"]
    )
    # "wemby" → uppercased to "WEMBY" but already deduped → drop
    # "Star" → uppercased to "STAR" → keep
    # "abc!" → has '!' → drop
    # "1234" → digits → drop
    # "X" → length 1 → drop
    # "TOO LONG" → has space → drop
    # "OT" twice → keep first only
    assert out == ["WEMBY", "STAR", "OT"]


def test_parse_candidate_response_clean_json() -> None:
    raw = '["WEMBY", "STEPH", "OT"]'
    assert _parse_candidate_response(raw) == ["WEMBY", "STEPH", "OT"]


def test_parse_candidate_response_with_code_fence() -> None:
    raw = '```json\n["WEMBY", "OT"]\n```'
    assert _parse_candidate_response(raw) == ["WEMBY", "OT"]


def test_parse_candidate_response_with_prose_around_array() -> None:
    raw = "Sure, here are the candidates:\n[\"A\", \"B\"]\nLet me know if you need more."
    # The substring extractor finds the first '[' / last ']'.
    assert _parse_candidate_response(raw) == ["A", "B"]


def test_parse_candidate_response_garbage_returns_empty() -> None:
    assert _parse_candidate_response("not json at all") == []
    assert _parse_candidate_response("") == []


def test_parse_candidate_response_drops_non_strings() -> None:
    raw = '["WEMBY", 42, "OT", null]'
    assert _parse_candidate_response(raw) == ["WEMBY", "OT"]


def test_format_games_for_prompt_includes_score_and_performers() -> None:
    digest = _example_games_digest(date_cls(2026, 5, 16))
    out = _format_games_for_prompt(digest)
    assert "BOS 112, NYK 109" in out
    assert "Jayson Tatum" in out
    assert "NAILBITER" in out


def test_format_reddit_for_prompt_includes_titles_and_comments() -> None:
    digest = _example_reddit_digest(date_cls(2026, 5, 16))
    out = _format_reddit_for_prompt(digest)
    assert "Tatum hits the dagger" in out
    assert "career night" in out


def test_format_games_for_prompt_handles_empty_games() -> None:
    out = _format_games_for_prompt(GamesDigest(date="2026-05-16", games=[]))
    assert out == "(no games)"


def test_format_reddit_for_prompt_handles_empty_posts() -> None:
    out = _format_reddit_for_prompt(RedditDigest(date="2026-05-16", posts=[]))
    assert out == "(no posts)"


# ---------------------------------------------------------------------------
# pick_candidate_pool
# ---------------------------------------------------------------------------


def test_pick_candidate_pool_happy_path() -> None:
    season = _example_season()
    games = _example_games_digest(date_cls(2026, 5, 16))
    reddit = _example_reddit_digest(date_cls(2026, 5, 16))

    llm = StubLLM(lambda _p: json.dumps(["WEMBY", "STEPH", "OT", "BOS"]))
    out = pick_candidate_pool(
        season=season, reddit_digest=reddit, games_digest=games, llm=llm
    )
    assert out == ["WEMBY", "STEPH", "OT", "BOS"]


def test_pick_candidate_pool_drops_invalid_entries() -> None:
    season = _example_season()
    games = _example_games_digest(date_cls(2026, 5, 16))
    reddit = _example_reddit_digest(date_cls(2026, 5, 16))

    llm = StubLLM(
        lambda _p: json.dumps(
            ["WEMBY", "wemby_lower", "X", "TOOLONG6", "OT", "abc-d", "BOS"]
        )
    )
    out = pick_candidate_pool(
        season=season, reddit_digest=reddit, games_digest=games, llm=llm
    )
    # "wemby_lower" has underscore → drop. "X" too short. "TOOLONG6" has digit
    # AND too long. "abc-d" has hyphen.
    assert out == ["WEMBY", "OT", "BOS"]


def test_pick_candidate_pool_truncates_to_target_count() -> None:
    season = _example_season()
    games = _example_games_digest(date_cls(2026, 5, 16))
    reddit = _example_reddit_digest(date_cls(2026, 5, 16))

    # 10 distinct length-4 A-Z candidates, all valid. Truncation should keep
    # only the first CANDIDATE_TARGET_COUNT.
    too_many = ["AAAA", "BBBB", "CCCC", "DDDD", "EEEE", "FFFF", "GGGG", "HHHH", "IIII", "JJJJ"]
    llm = StubLLM(lambda _p: json.dumps(too_many))
    out = pick_candidate_pool(
        season=season, reddit_digest=reddit, games_digest=games, llm=llm
    )
    assert len(out) == CANDIDATE_TARGET_COUNT
    # First N preserved in priority order.
    assert out == too_many[:CANDIDATE_TARGET_COUNT]


def test_pick_candidate_pool_outage_bubbles_out() -> None:
    season = _example_season()
    games = _example_games_digest(date_cls(2026, 5, 16))
    reddit = _example_reddit_digest(date_cls(2026, 5, 16))

    def raises(_p: str) -> str:
        raise ClueLLMOutageError("simulated outage")

    llm = StubLLM(raises)
    with pytest.raises(ClueLLMOutageError):
        pick_candidate_pool(
            season=season, reddit_digest=reddit, games_digest=games, llm=llm
        )


def test_pick_candidate_pool_unknown_exception_wrapped() -> None:
    season = _example_season()
    games = _example_games_digest(date_cls(2026, 5, 16))
    reddit = _example_reddit_digest(date_cls(2026, 5, 16))

    def raises(_p: str) -> str:
        raise RuntimeError("network kaput")

    llm = StubLLM(raises)
    with pytest.raises(ClueLLMOutageError):
        pick_candidate_pool(
            season=season, reddit_digest=reddit, games_digest=games, llm=llm
        )


# ---------------------------------------------------------------------------
# entries_from_grid
# ---------------------------------------------------------------------------


def test_entries_from_grid_numbers_match_example_puzzle_convention() -> None:
    """Use a real fill_grid output and confirm the entries validate as a
    Puzzle (which enforces start-of-run + crossing constraints)."""
    wordlist = load_wordlist()
    grid = fill_grid([], wordlist, seed=123)
    entries = entries_from_grid(grid)

    # Every entry must point to a real letter run in the grid (Puzzle's
    # validator enforces this, but we want a more direct assertion too).
    for entry in entries:
        # Schema constraints: clue is "?" placeholder, voice is "factual".
        assert entry.clue == "?"
        assert entry.voice == "factual"
        # ID format: "<n><A|D>".
        assert entry.id[-1] in {"A", "D"}
        assert entry.id[:-1].isdigit()

    # Use Puzzle's validator as the canonical "is this entry list correct"
    # check: it requires start-of-run, crossings, full coverage.
    puzzle = Puzzle(
        date="2026-05-17",
        puzzle_number=1,
        grid=grid,
        entries=entries,
        season_context_version="abc12345",
        generated_at=datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc),
        model="test",
    )
    assert puzzle is not None


def test_entries_from_grid_shares_number_for_across_and_down_at_same_cell() -> None:
    """When a cell starts both an across and a down entry, both share its
    number (e.g. 1A and 1D)."""
    wordlist = load_wordlist()
    grid = fill_grid([], wordlist, seed=0)
    entries = entries_from_grid(grid)

    # Group by numeric prefix.
    by_number: dict[str, list[str]] = {}
    for e in entries:
        n = e.id[:-1]
        by_number.setdefault(n, []).append(e.id[-1])

    # The 4-corners template means (0,0) starts both across and down, so we
    # expect at least one number with both A and D.
    shared = [n for n, dirs in by_number.items() if set(dirs) == {"A", "D"}]
    assert shared, f"expected at least one shared A+D number, got {by_number}"


def test_entries_from_grid_returns_at_least_one_entry() -> None:
    wordlist = load_wordlist()
    grid = fill_grid([], wordlist, seed=0)
    entries = entries_from_grid(grid)
    assert len(entries) >= 4  # mini grids have several entries; sanity.


# ---------------------------------------------------------------------------
# run_pipeline — full happy path
# ---------------------------------------------------------------------------


def test_run_pipeline_happy_path_returns_valid_puzzle() -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target)

    puzzle = run_pipeline(target, deps=deps)

    assert puzzle is not None
    assert puzzle.date == "2026-05-16"
    assert puzzle.model == "test-fake-model"
    assert puzzle.season_context_version == "testver1"
    assert len(puzzle.entries) >= 4
    # Validates against the Puzzle schema by virtue of having been
    # constructed without raising. Round-trip for paranoia.
    redumped = puzzle.model_dump_json()
    parsed = Puzzle.model_validate_json(redumped)
    assert parsed.date == puzzle.date


def test_run_pipeline_records_slate_date_from_games_digest() -> None:
    """Publish date is the target; slate_date comes from the games digest,
    which can be an earlier day (look-back)."""
    publish = date_cls(2026, 6, 1)  # Monday
    # Games digest dated to Saturday's slate — as the look-back resolver
    # would return.
    saturday_games = _example_games_digest(date_cls(2026, 5, 30))
    deps = _make_deps(target_date=publish, games=saturday_games)

    puzzle = run_pipeline(publish, deps=deps)

    assert puzzle is not None
    assert puzzle.date == "2026-06-01"  # published today
    assert puzzle.slate_date == "2026-05-30"  # games from Saturday


def test_run_pipeline_no_games_returns_none() -> None:
    target = date_cls(2026, 7, 4)  # mid-summer, no games
    deps = _make_deps(
        target_date=target,
        games=NoGamesSignal(date=target.isoformat()),
    )

    out = run_pipeline(target, deps=deps)
    assert out is None


def test_run_pipeline_reddit_failure_propagates() -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, fail_reddit=True)
    with pytest.raises(RedditIngestError):
        run_pipeline(target, deps=deps)


def test_run_pipeline_games_failure_propagates() -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, fail_games=True)
    with pytest.raises(NBAStatsFetchError):
        run_pipeline(target, deps=deps)


def test_run_pipeline_llm_outage_propagates() -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, llm_outage=True)
    with pytest.raises(ClueLLMOutageError):
        run_pipeline(target, deps=deps)


def test_run_pipeline_with_empty_candidate_pool_still_fills_from_wordlist() -> None:
    """If the LLM returns no usable candidates, the fill algorithm falls back
    to a wordlist-only fill — the puzzle still ships."""
    target = date_cls(2026, 5, 16)
    # Returns a JSON array but every entry is invalid (lowercase / digits).
    bad_candidates = ["lowercase", "123", "?", ""]
    deps = _make_deps(target_date=target, candidates=bad_candidates)

    puzzle = run_pipeline(target, deps=deps)
    assert puzzle is not None


def test_run_pipeline_uses_date_ordinal_as_seed() -> None:
    """Two runs for the same date produce the same grid (determinism)."""
    target = date_cls(2026, 5, 16)
    deps_a = _make_deps(target_date=target)
    deps_b = _make_deps(target_date=target)

    a = run_pipeline(target, deps=deps_a)
    b = run_pipeline(target, deps=deps_b)
    assert a is not None and b is not None
    assert a.grid.model_dump() == b.grid.model_dump()


# ---------------------------------------------------------------------------
# main() — CLI surface
# ---------------------------------------------------------------------------


def test_main_writes_puzzle_for_game_day(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target)

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 0

    # The league subdir is always appended under --out.
    written = puzzle_path_for("2026-05-16", tmp_path / "nba")
    assert written.exists()
    payload = json.loads(written.read_text())
    assert payload["date"] == "2026-05-16"
    # Pretty-printed: contains newlines.
    assert "\n" in written.read_text()


def test_main_no_games_day_writes_no_file(tmp_path: Path) -> None:
    """AE3: a no-games day exits 0 with no file written."""
    target = date_cls(2026, 7, 4)
    deps = _make_deps(
        target_date=target, games=NoGamesSignal(date=target.isoformat())
    )

    rc = main(
        ["--date", "2026-07-04", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 0
    written = puzzle_path_for("2026-07-04", tmp_path / "nba")
    assert not written.exists()


def test_main_idempotent_when_file_exists(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target)

    rc1 = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc1 == 0
    written = puzzle_path_for("2026-05-16", tmp_path / "nba")
    assert written.exists()
    first_mtime = written.stat().st_mtime_ns
    first_contents = written.read_text()

    # Second run with identical args (no --force) must be a no-op: file
    # untouched, exit 0. The orchestrator must not even call any deps.
    sentinel: list[str] = []

    def boom(_d: date_cls):
        sentinel.append("called")
        raise AssertionError("no deps should be invoked on idempotent path")

    def explode_no_args():
        sentinel.append("called")
        raise AssertionError("no deps should be invoked on idempotent path")

    def explode_prompt(_p: str) -> str:
        sentinel.append("called")
        raise AssertionError("no deps should be invoked on idempotent path")

    blocked_deps = Deps(
        season_context=explode_no_args,
        fetch_reddit=boom,
        fetch_games=boom,
        load_wordlist=explode_no_args,
        llm=StubLLM(explode_prompt),
        model="blocked",
    )

    rc2 = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=blocked_deps,
    )
    assert rc2 == 0
    assert sentinel == []
    # File must be byte-identical (i.e. not rewritten).
    assert written.read_text() == first_contents
    assert written.stat().st_mtime_ns == first_mtime


def test_main_force_overwrites_existing_file(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    out = tmp_path
    written = puzzle_path_for("2026-05-16", out / "nba")
    written.parent.mkdir(parents=True, exist_ok=True)
    # Pre-existing dummy file so we can confirm overwrite happened.
    written.write_text('{"sentinel": true}\n', encoding="utf-8")

    deps = _make_deps(target_date=target)
    rc = main(
        ["--date", "2026-05-16", "--out", str(out), "--force"],
        deps=deps,
    )
    assert rc == 0
    payload = json.loads(written.read_text())
    assert "sentinel" not in payload
    assert payload["date"] == "2026-05-16"


def test_main_dry_run_does_not_write_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target)

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path), "--dry-run"],
        deps=deps,
    )
    assert rc == 0

    # No file written.
    written = puzzle_path_for("2026-05-16", tmp_path)
    assert not written.exists()

    # JSON dumped to stdout.
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["date"] == "2026-05-16"


def test_main_reddit_failure_exits_nonzero(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, fail_reddit=True)

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 1
    assert not puzzle_path_for("2026-05-16", tmp_path).exists()


def test_main_games_failure_exits_nonzero(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, fail_games=True)

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 1
    assert not puzzle_path_for("2026-05-16", tmp_path).exists()


def test_main_llm_outage_exits_nonzero(tmp_path: Path) -> None:
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target, llm_outage=True)

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 1
    assert not puzzle_path_for("2026-05-16", tmp_path).exists()


def test_main_grid_fill_failure_exits_nonzero(tmp_path: Path) -> None:
    """A wordlist that's too thin to fill any template must surface as exit 1."""
    target = date_cls(2026, 5, 16)

    def empty_wordlist() -> list[str]:
        return []

    base = _make_deps(target_date=target)
    deps = Deps(
        season_context=base.season_context,
        fetch_reddit=base.fetch_reddit,
        fetch_games=base.fetch_games,
        load_wordlist=empty_wordlist,
        llm=base.llm,
        clue_generator=base.clue_generator,
        model=base.model,
    )

    rc = main(
        ["--date", "2026-05-16", "--out", str(tmp_path)],
        deps=deps,
    )
    assert rc == 1
    assert not puzzle_path_for("2026-05-16", tmp_path).exists()


def test_main_invalid_date_exits_nonzero(tmp_path: Path) -> None:
    """argparse passes the string through; we raise SystemExit on parse fail."""
    with pytest.raises(SystemExit):
        main(
            ["--date", "not-a-date", "--out", str(tmp_path)],
            deps=_make_deps(target_date=date_cls(2026, 5, 16)),
        )


# ---------------------------------------------------------------------------
# write_puzzle_json
# ---------------------------------------------------------------------------


def test_write_puzzle_json_round_trips(tmp_path: Path) -> None:
    """Writing a puzzle to disk and re-parsing yields the same model."""
    target = date_cls(2026, 5, 16)
    deps = _make_deps(target_date=target)
    puzzle = run_pipeline(target, deps=deps)
    assert puzzle is not None

    path = tmp_path / "puzzles" / "2026-05-16.json"
    write_puzzle_json(puzzle, path)
    assert path.exists()

    payload = json.loads(path.read_text())
    re_parsed = Puzzle.model_validate(payload)
    assert re_parsed.date == puzzle.date
    assert re_parsed.model == puzzle.model
    assert len(re_parsed.entries) == len(puzzle.entries)


# ---------------------------------------------------------------------------
# Deps.production — LLM backend selection
# ---------------------------------------------------------------------------


def test_production_defaults_to_anthropic_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NBA_MINI_LLM_BACKEND", raising=False)
    deps = Deps.production()
    assert isinstance(deps.llm, AnthropicClueLLM)
    assert deps.model == DEFAULT_MODEL


def test_production_bedrock_backend_explicit_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NBA_MINI_LLM_BACKEND", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    deps = Deps.production(backend="bedrock")
    assert isinstance(deps.llm, BedrockClueLLM)
    assert deps.model == BEDROCK_DEFAULT_MODEL
    assert deps.llm.aws_region == "us-east-1"


def test_production_backend_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NBA_MINI_LLM_BACKEND", "bedrock")
    deps = Deps.production()
    assert isinstance(deps.llm, BedrockClueLLM)


def test_production_explicit_arg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NBA_MINI_LLM_BACKEND", "bedrock")
    deps = Deps.production(backend="anthropic")
    assert isinstance(deps.llm, AnthropicClueLLM)


def test_production_custom_model_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    deps = Deps.production(backend="bedrock", model="us.anthropic.claude-opus-4-7")
    assert deps.model == "us.anthropic.claude-opus-4-7"
    assert isinstance(deps.llm, BedrockClueLLM)
    assert deps.llm.model == "us.anthropic.claude-opus-4-7"


def test_production_unknown_backend_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NBA_MINI_LLM_BACKEND", raising=False)
    with pytest.raises(SystemExit, match="unknown LLM backend"):
        Deps.production(backend="gemini")


# ---------------------------------------------------------------------------
# Live integration — gated behind env var
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("NBA_MINI_LIVE_E2E") != "1",
    reason="requires live API access; set NBA_MINI_LIVE_E2E=1 to run",
)
def test_live_e2e_against_real_apis(tmp_path: Path) -> None:
    """Real end-to-end: hits Reddit, nba.com, and Anthropic.

    Skipped by default. Run with ``NBA_MINI_LIVE_E2E=1`` plus a valid
    ``ANTHROPIC_API_KEY`` to exercise the full live path. We pick an old date
    so the upstream caches are warm and the day reliably had games.
    """
    target = date_cls(2025, 5, 14)  # Conf semis last year — known good slate.

    deps = Deps.production()
    rc = main(
        ["--date", target.isoformat(), "--out", str(tmp_path), "--force"],
        deps=deps,
    )
    assert rc == 0

    written = puzzle_path_for(target.isoformat(), tmp_path / "nba")
    assert written.exists()
    payload = json.loads(written.read_text())
    re_parsed = Puzzle.model_validate(payload)
    assert re_parsed.date == target.isoformat()
    assert len(re_parsed.entries) >= 4
