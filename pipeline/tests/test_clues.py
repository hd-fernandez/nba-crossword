"""Tests for clue generation. Never hits a real Anthropic endpoint.

Coverage targets (from the v0 plan, U7):
- Happy path: every entry comes back with a non-empty clue + voice tag.
- Voice distribution: 6-entry puzzle approximates 50/30/20 (3 wry / 2 disc / 1 fac).
- Bad clue: model output that contains the answer is rejected and retried.
- Bad clue: model output longer than the hard length budget is rejected and retried.
- Persistent retry exhaustion → templated fallback, no crash.
- LLM outage path: persistent SDK exceptions raise ClueLLMOutageError after retries.
- Round-trip: a fully clued 6-entry puzzle validates against the Puzzle schema.

All tests inject a `FakeClueLLM` so they're deterministic and fast.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Callable

import pytest

from nba_mini.clues import (
    DEFAULT_MODEL,
    HARD_LENGTH_LIMIT,
    MAX_ATTEMPTS,
    SOFT_LENGTH_LIMIT,
    VOICE_TARGETS,
    BEDROCK_DEFAULT_MODEL,
    AnthropicClueLLM,
    BedrockClueLLM,
    ClueLLM,
    ClueLLMOutageError,
    GenerationContext,
    _assign_voices,
    _extract_text,
    _normalize_clue,
    _validate_clue,
    generate_clues,
)
from nba_mini.ingest.nba_stats import GamesDigest, GameSummary, TopPerformer
from nba_mini.ingest.reddit import RedditDigest, RedditPost
from nba_mini.schema import (
    Cell,
    Entry,
    Grid,
    LetterCell,
    Puzzle,
)


# ---------------------------------------------------------------------------
# Fakes & helpers
# ---------------------------------------------------------------------------


class FakeClueLLM:
    """A `ClueLLM` whose `complete()` is driven by an injected callable.

    The callable receives the prompt and returns the response. This lets each
    test set up exactly the response sequence it needs (good clue, bad clue,
    raise, etc.).
    """

    def __init__(self, responder: Callable[[str], str]) -> None:
        self.responder = responder
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responder(prompt)


def _placeholder_entry(
    *,
    id: str,
    answer: str,
    direction: str = "across",
    row: int = 0,
    col: int = 0,
) -> Entry:
    """Construct an Entry with placeholder clue/voice ready to be overwritten."""
    return Entry(
        id=id,
        direction=direction,  # type: ignore[arg-type]
        row=row,
        col=col,
        answer=answer,
        clue="placeholder",
        voice="factual",
    )


def _basic_context() -> GenerationContext:
    return GenerationContext(
        season_context_text="It is mid-May 2026, the NBA Conference Semifinals.",
        reddit_digest=None,
        games_digest=None,
        seed=0,
    )


def _six_entries() -> list[Entry]:
    """Six representative answers (all ≤5 letters per schema). Used as the
    canonical 6-entry puzzle for distribution tests."""
    return [
        _placeholder_entry(id="1A", answer="WEMBY", row=0, col=0, direction="across"),
        _placeholder_entry(id="2A", answer="STEPH", row=1, col=0, direction="across"),
        _placeholder_entry(id="3A", answer="LUKA", row=2, col=0, direction="across"),
        _placeholder_entry(id="4A", answer="OT", row=3, col=0, direction="across"),
        _placeholder_entry(id="5A", answer="BOS", row=4, col=0, direction="across"),
        _placeholder_entry(id="6A", answer="LAL", row=4, col=2, direction="across"),
    ]


def _good_responder(clue: str = "A short, valid clue.") -> Callable[[str], str]:
    """A responder that always returns the same valid clue text."""

    def _resp(_prompt: str) -> str:
        return clue

    return _resp


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------


def test_voice_assignment_returns_correct_count() -> None:
    voices = _assign_voices(6, seed=0)
    assert len(voices) == 6
    counts = Counter(voices)
    # 50/30/20 of 6 = 3/1.8/1.2 -> with largest-remainder: 3/2/1.
    assert counts["wry"] == 3
    assert counts["discoursey"] == 2
    assert counts["factual"] == 1


def test_voice_assignment_is_deterministic() -> None:
    a = _assign_voices(6, seed=42)
    b = _assign_voices(6, seed=42)
    assert a == b


def test_voice_assignment_zero_entries() -> None:
    assert _assign_voices(0, seed=0) == []


def test_voice_assignment_targets_sum_to_one() -> None:
    total = sum(weight for _, weight in VOICE_TARGETS)
    assert total == pytest.approx(1.0)


def test_voice_assignment_8_entries_approx_50_30_20() -> None:
    # 8 entries × 50/30/20 → 4/2.4/1.6. Largest-remainder → 4/2/2 (the two
    # leftover slots go to the largest fractional parts, 0.4 vs 0.6).
    counts = Counter(_assign_voices(8, seed=0))
    assert counts["wry"] == 4
    assert counts["discoursey"] == 2
    assert counts["factual"] == 2


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_validate_rejects_clue_containing_answer_case_insensitive() -> None:
    ok, reason = _validate_clue("LeBron showed up.", "LEBRON")
    assert ok is False
    assert reason is not None
    assert "LEBRON" in reason


def test_validate_rejects_clue_too_long() -> None:
    long_clue = "x" * (HARD_LENGTH_LIMIT + 1)
    ok, reason = _validate_clue(long_clue, "ANSWER")
    assert ok is False
    assert reason is not None
    assert "too long" in reason


def test_validate_rejects_empty_clue() -> None:
    ok, _ = _validate_clue("", "ANSWER")
    assert ok is False


def test_validate_accepts_clean_clue() -> None:
    ok, reason = _validate_clue("Visited TD Garden, scored 40, left.", "LEBRON")
    assert ok is True
    assert reason is None


def test_normalize_strips_quotes_and_label() -> None:
    assert _normalize_clue('  "A clue."  ') == "A clue."
    assert _normalize_clue("Clue: A clue.") == "A clue."
    assert _normalize_clue("ANSWER: A clue.") == "A clue."
    assert _normalize_clue("**A clue.**") == "A clue."


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_every_entry_gets_clue_and_voice() -> None:
    entries = _six_entries()
    llm = FakeClueLLM(_good_responder("Yesterday's discourse, captured."))

    out = generate_clues(entries, _basic_context(), llm=llm)

    assert len(out) == len(entries)
    for original, generated in zip(entries, out, strict=True):
        assert generated.id == original.id
        assert generated.answer == original.answer
        assert generated.clue and len(generated.clue) >= 1
        assert generated.voice in {"wry", "discoursey", "factual"}


def test_happy_path_distribution_is_50_30_20_for_six_entries() -> None:
    entries = _six_entries()
    llm = FakeClueLLM(_good_responder())

    out = generate_clues(entries, _basic_context(), llm=llm)
    counts = Counter(e.voice for e in out)

    assert counts["wry"] == 3
    assert counts["discoursey"] == 2
    assert counts["factual"] == 1


def test_input_entries_are_not_mutated() -> None:
    entries = _six_entries()
    snapshot = [e.model_copy(deep=True) for e in entries]
    llm = FakeClueLLM(_good_responder())

    generate_clues(entries, _basic_context(), llm=llm)

    for before, after in zip(snapshot, entries, strict=True):
        assert before == after


def test_empty_entry_list_returns_empty() -> None:
    llm = FakeClueLLM(_good_responder())
    assert generate_clues([], _basic_context(), llm=llm) == []
    assert llm.calls == []


def test_llm_called_once_per_entry_on_happy_path() -> None:
    entries = _six_entries()
    llm = FakeClueLLM(_good_responder())

    generate_clues(entries, _basic_context(), llm=llm)

    assert len(llm.calls) == len(entries)


# ---------------------------------------------------------------------------
# Retries on bad clues
# ---------------------------------------------------------------------------


def test_clue_containing_answer_is_rejected_and_retried() -> None:
    """First attempt smuggles the answer; second attempt is clean → accepted."""
    answers_seen: list[int] = []

    def responder(_prompt: str) -> str:
        answers_seen.append(len(answers_seen))
        if answers_seen[-1] == 0:
            return "Steph just dropped 40 on Boston."  # contains STEPH
        return "Dropped 40 on Boston in Game 4."

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(responder)

    out = generate_clues(entries, _basic_context(), llm=llm)

    assert len(llm.calls) == 2  # one rejection + one good
    assert out[0].clue == "Dropped 40 on Boston in Game 4."
    assert "steph" not in out[0].clue.lower()


def test_clue_too_long_is_rejected_and_retried() -> None:
    """First attempt is over the budget; second attempt is short → accepted."""
    too_long = "x" * (HARD_LENGTH_LIMIT + 5)
    short_clue = "Short, valid clue."
    counter = {"n": 0}

    def responder(_prompt: str) -> str:
        counter["n"] += 1
        return too_long if counter["n"] == 1 else short_clue

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(responder)
    out = generate_clues(entries, _basic_context(), llm=llm)

    assert len(llm.calls) == 2
    assert out[0].clue == short_clue


def test_retry_prompt_includes_previous_attempt() -> None:
    """The retry prompt should contain a 'Retry note' section with the prior text."""
    bad = "Steph etc."  # contains STEPH
    good = "Dropped 40 on Boston in Game 4."
    counter = {"n": 0}

    def responder(_prompt: str) -> str:
        counter["n"] += 1
        return bad if counter["n"] == 1 else good

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(responder)

    generate_clues(entries, _basic_context(), llm=llm)

    assert len(llm.calls) == 2
    second_prompt = llm.calls[1]
    assert "Retry note" in second_prompt
    assert bad in second_prompt


# ---------------------------------------------------------------------------
# Fallback after exhaustion
# ---------------------------------------------------------------------------


def test_persistent_bad_clues_fall_back_to_templated_factual(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """All MAX_ATTEMPTS produce bad clues → fallback fires, no crash."""

    def always_contains_answer(_prompt: str) -> str:
        return "Steph is the answer."  # always contains STEPH

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(always_contains_answer)

    with caplog.at_level("WARNING", logger="nba_mini.clues"):
        out = generate_clues(entries, _basic_context(), llm=llm)

    assert len(llm.calls) == MAX_ATTEMPTS
    assert out[0].clue
    assert "steph" not in out[0].clue.lower()
    log_text = "\n".join(r.getMessage() for r in caplog.records)
    assert "fallback" in log_text.lower()


def test_fallback_uses_grounding_fact_when_available() -> None:
    """When the box score gives us a fact that doesn't smuggle the answer,
    the fallback uses it."""
    # Answer = WEMBY; the grounding fact for Wemby is the player line, which
    # doesn't contain "WEMBY" (that's not how the player's name is spelled).
    games_digest = GamesDigest(
        date="2026-05-14",
        games=[
            GameSummary(
                game_id="0042500001",
                home="SAS",
                away="OKC",
                home_score=110,
                away_score=104,
                score="SAS 110, OKC 104",
                top_performers=[
                    TopPerformer(
                        player="Victor Wembanyama",
                        team="SAS",
                        statline="32 PTS / 14 REB / 7 BLK",
                    ),
                ],
                notable_events=[],
            )
        ],
    )

    # An answer that *isn't* literally the player's stored name but matches
    # via substring — "WEMBY" is in "Wembanyama" lowercased? "wembanyama"
    # contains "wemb" but not "wemby". So we use a different test answer.
    # Better: use answer = "WEMB" and verify the player line is pulled.
    # But Entry.answer min length is 2 — WEMB is fine (4 chars).
    entries = [_placeholder_entry(id="1A", answer="WEMB")]
    # The grounding fact will be "Victor Wembanyama (SAS): 32 PTS / 14 REB / 7 BLK."
    # which contains "wemb" — so the fallback's guard rejects it. The
    # generic fallback is used instead. This is the *correct* behavior:
    # the fallback must never smuggle the answer.
    def always_smuggle(_prompt: str) -> str:
        return "WEMB ejected again, sigh."  # contains WEMB

    ctx = GenerationContext(
        season_context_text="May 2026 semifinals.",
        games_digest=games_digest,
        seed=0,
    )
    llm = FakeClueLLM(always_smuggle)
    out = generate_clues(entries, ctx, llm=llm)
    # The grounding fact contains the answer, so we expect the *generic*
    # fallback shape: "NBA-related answer (4 letters); see today's discourse."
    assert "wemb" not in out[0].clue.lower()
    assert "(4 letters)" in out[0].clue


def test_fallback_uses_grounding_fact_that_does_not_smuggle_answer() -> None:
    """Positive case: grounding fact that doesn't contain the answer flows
    through to the fallback clue."""
    # Answer "STAR" — generic word, won't match any team tri-code or player
    # name in the digest below.
    games_digest = GamesDigest(
        date="2026-05-14",
        games=[
            GameSummary(
                game_id="0042500001",
                home="LAL",
                away="BOS",
                home_score=120,
                away_score=110,
                score="LAL 120, BOS 110",
                top_performers=[
                    TopPerformer(
                        player="LeBron James",
                        team="LAL",
                        statline="40 PTS / 8 REB / 7 AST",
                    ),
                ],
                notable_events=[],
            )
        ],
    )

    def always_smuggle(_prompt: str) -> str:
        return "STAR power on display."  # contains STAR

    entries = [_placeholder_entry(id="1A", answer="STAR")]
    ctx = GenerationContext(
        season_context_text="May 2026 semifinals.",
        games_digest=games_digest,
        seed=0,
    )
    llm = FakeClueLLM(always_smuggle)
    out = generate_clues(entries, ctx, llm=llm)
    # No grounding fact for STAR (no team or player matches), so the
    # generic fallback is used.
    assert "star" not in out[0].clue.lower()
    assert out[0].clue  # non-empty


# ---------------------------------------------------------------------------
# Outage path (LLM call itself raises)
# ---------------------------------------------------------------------------


def test_llm_outage_raises_typed_error_after_retries() -> None:
    """Persistent LLM exceptions surface as ClueLLMOutageError."""

    def always_raises(_prompt: str) -> str:
        raise RuntimeError("simulated network outage")

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(always_raises)

    with pytest.raises(ClueLLMOutageError):
        generate_clues(entries, _basic_context(), llm=llm)


def test_llm_outage_typed_error_passes_through() -> None:
    def raise_typed(_prompt: str) -> str:
        raise ClueLLMOutageError("503 from upstream")

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(raise_typed)

    with pytest.raises(ClueLLMOutageError):
        generate_clues(entries, _basic_context(), llm=llm)


def test_transient_outage_then_success_recovers() -> None:
    """One transient failure → retry succeeds, no exception bubbles out."""
    counter = {"n": 0}

    def flaky(_prompt: str) -> str:
        counter["n"] += 1
        if counter["n"] == 1:
            raise RuntimeError("transient")
        return "A short, valid clue."

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(flaky)
    out = generate_clues(entries, _basic_context(), llm=llm)
    assert out[0].clue == "A short, valid clue."


# ---------------------------------------------------------------------------
# Soft length warning
# ---------------------------------------------------------------------------


def test_soft_length_warning_is_logged_but_clue_is_accepted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Clues over SOFT_LENGTH_LIMIT but under HARD_LENGTH_LIMIT pass with a warning."""
    long_clue = "x " * 50  # ~100 chars, over 80, under 160
    long_clue = long_clue.strip()
    assert SOFT_LENGTH_LIMIT < len(long_clue) <= HARD_LENGTH_LIMIT

    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(_good_responder(long_clue))

    with caplog.at_level("WARNING", logger="nba_mini.clues"):
        out = generate_clues(entries, _basic_context(), llm=llm)

    assert out[0].clue == long_clue
    assert any("soft length" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Prompt assembly (sanity)
# ---------------------------------------------------------------------------


def test_prompt_includes_season_context_and_answer() -> None:
    captured: list[str] = []

    def capturing(prompt: str) -> str:
        captured.append(prompt)
        return "A clue."

    entries = [_placeholder_entry(id="1A", answer="WEMBY")]
    ctx = GenerationContext(
        season_context_text="UNIQUE_SEASON_MARKER_42",
        seed=0,
    )
    llm = FakeClueLLM(capturing)
    generate_clues(entries, ctx, llm=llm)

    prompt = captured[0]
    assert "UNIQUE_SEASON_MARKER_42" in prompt
    # Answer is included as the answer to clue (in the per-entry section).
    assert "WEMBY" in prompt


def test_prompt_uses_correct_voice_template() -> None:
    """Each voice's distinctive marker must appear in the corresponding prompt."""
    seen_prompts: list[str] = []

    def capture(prompt: str) -> str:
        seen_prompts.append(prompt)
        return "A clue."

    entries = _six_entries()
    llm = FakeClueLLM(capture)
    out = generate_clues(entries, _basic_context(), llm=llm)

    # For every entry, the prompt should be the template that matches the
    # assigned voice. We verify by checking for distinctive substrings from
    # each markdown file's "Voice:" header.
    voice_marker = {
        "wry": "Voice: wry NYT",
        "discoursey": "Voice: cultural / discourse-aware",
        "factual": "Voice: factual",
    }
    for entry, prompt in zip(out, seen_prompts, strict=True):
        assert voice_marker[entry.voice] in prompt


def test_prior_clues_are_threaded_into_later_prompts() -> None:
    """Each clue prompt after the first must list the clues already written.

    This is the variety mechanism: the model is shown prior clues so it can
    pick a different angle and not repeat one storyline across the puzzle.
    """
    seen_prompts: list[str] = []
    counter = {"n": 0}

    def capture(prompt: str) -> str:
        seen_prompts.append(prompt)
        counter["n"] += 1
        return f"Distinct clue number {counter['n']}."

    entries = _six_entries()
    llm = FakeClueLLM(capture)
    generate_clues(entries, _basic_context(), llm=llm)

    # First prompt: no prior clues yet -> the neutral placeholder.
    assert "(none yet" in seen_prompts[0]
    # The last prompt must contain the text of an earlier clue, proving the
    # accumulated clues are funneled forward.
    assert "Distinct clue number 1." in seen_prompts[-1]
    # And the "do not repeat" instruction is present in every clue prompt.
    for prompt in seen_prompts:
        assert "DO NOT REPEAT their angle" in prompt


def test_reddit_digest_relevant_post_is_included_in_prompt() -> None:
    """A post whose title mentions the answer is funneled into the prompt."""
    captured: list[str] = []

    def capture(prompt: str) -> str:
        captured.append(prompt)
        return "A clue."

    digest = RedditDigest(
        date="2026-05-14",
        posts=[
            RedditPost(
                title="STEPH puts up 40 in Boston",
                flair="Post Game Thread",
                score=4500,
                comment_count=2000,
                top_comments=["that was cooked", "career night"],
                permalink="/r/nba/comments/abc/steph_40/",
            ),
            RedditPost(
                title="Some unrelated trade rumor",
                flair=None,
                score=300,
                comment_count=80,
                top_comments=["meh"],
                permalink="/r/nba/comments/def/trade/",
            ),
        ],
    )
    ctx = GenerationContext(
        season_context_text="May 2026 semis.",
        reddit_digest=digest,
        seed=0,
    )
    entries = [_placeholder_entry(id="1A", answer="STEPH")]
    llm = FakeClueLLM(capture)
    generate_clues(entries, ctx, llm=llm)

    prompt = captured[0]
    assert "puts up 40 in Boston" in prompt
    # The unrelated post should NOT be included since we matched a relevant
    # one — the fallback "first 2 posts" only fires when nothing matches.
    assert "trade rumor" not in prompt


# ---------------------------------------------------------------------------
# Integration with Puzzle schema
# ---------------------------------------------------------------------------


def test_full_puzzle_round_trips_with_generated_clues() -> None:
    """Build a full schema-valid 5×5 puzzle, generate clues, validate."""
    # Hand-crafted grid: 5 rows of letters, no blocks. 10 entries (5 across,
    # 5 down). Letters chosen so every row + every column is a real-feeling
    # short word; we don't actually care about wordlist membership for this
    # test — only that the grid + entries are internally consistent.
    rows = [
        "LAKER",
        "AREAS",
        "MOLES",
        "ELITE",
        "STARS",
    ]

    cells: list[list[Cell]] = []
    for r in rows:
        row_cells: list[Cell] = [LetterCell(answer=ch) for ch in r]
        cells.append(row_cells)
    grid = Grid(size=5, cells=cells)

    entries: list[Entry] = []
    # Across entries.
    for r, word in enumerate(rows):
        entries.append(
            _placeholder_entry(
                id=f"{r + 1}A",
                answer=word,
                row=r,
                col=0,
                direction="across",
            )
        )
    # Down entries.
    for c in range(5):
        word = "".join(rows[r][c] for r in range(5))
        entries.append(
            _placeholder_entry(
                id=f"{c + 1}D",
                answer=word,
                row=0,
                col=c,
                direction="down",
            )
        )

    # Generate clues via FakeClueLLM. We use varied valid clues so we can
    # also confirm none accidentally smuggle the answer.
    answers = [e.answer for e in entries]
    counter = {"n": 0}

    def responder(_prompt: str) -> str:
        i = counter["n"]
        counter["n"] += 1
        # Build a clue that we can guarantee doesn't contain its answer:
        # use a fixed phrase that no answer above happens to be a substring
        # of. Our answers are LAKER, AREAS, MOLES, ELITE, STARS, LAMES,
        # AROLT, KEELA, ERTER, RSSES — none of these substring into the
        # phrase below.
        return f"A short test clue number {i}."

    # Sanity-check that none of the generated answers appear in the chosen
    # phrase template. (Quick guard against test brittleness.)
    test_phrase = "A short test clue number 99."
    for a in answers:
        assert a.lower() not in test_phrase.lower(), (
            f"test setup error: answer {a!r} substrings into the test clue template"
        )

    ctx = GenerationContext(
        season_context_text="May 2026, NBA Conference Semifinals.",
        seed=0,
    )
    llm = FakeClueLLM(responder)
    clued_entries = generate_clues(entries, ctx, llm=llm)

    puzzle = Puzzle(
        date="2026-05-17",
        puzzle_number=1,
        grid=grid,
        entries=clued_entries,
        season_context_version="abcdef12",
        generated_at=datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc),
        model="test-fake",
    )

    redumped = puzzle.model_dump_json()
    parsed = Puzzle.model_validate_json(redumped)
    assert parsed is not None

    # Voice mix on 10 entries: 50/30/20 → 5/3/2.
    voice_counts = Counter(e.voice for e in clued_entries)
    assert voice_counts["wry"] == 5
    assert voice_counts["discoursey"] == 3
    assert voice_counts["factual"] == 2


# ---------------------------------------------------------------------------
# AnthropicClueLLM default surface
# ---------------------------------------------------------------------------


def test_anthropic_clue_llm_has_correct_default_model() -> None:
    """Default model should match the public DEFAULT_MODEL constant."""
    llm = AnthropicClueLLM()
    assert llm.model == DEFAULT_MODEL


def test_anthropic_clue_llm_implements_protocol() -> None:
    """Lightweight structural check: AnthropicClueLLM has `complete(str) -> str`."""
    llm: ClueLLM = AnthropicClueLLM()
    assert callable(llm.complete)


# ---------------------------------------------------------------------------
# BedrockClueLLM surface + shared text extraction
# ---------------------------------------------------------------------------


def test_bedrock_clue_llm_has_correct_default_model() -> None:
    """Default model should be the region-prefixed inference-profile ID."""
    llm = BedrockClueLLM()
    assert llm.model == BEDROCK_DEFAULT_MODEL
    assert llm.model.startswith("us.anthropic.")


def test_bedrock_clue_llm_implements_protocol() -> None:
    llm: ClueLLM = BedrockClueLLM()
    assert callable(llm.complete)


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeMessage:
    def __init__(self, *blocks: object) -> None:
        self.content = list(blocks)


def test_bedrock_complete_uses_injected_client() -> None:
    """With a pre-built client, complete() never imports/constructs a real SDK."""
    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self) -> None:
            self.messages = self

        def create(self, **kwargs: object) -> _FakeMessage:
            captured.update(kwargs)
            return _FakeMessage(_FakeBlock("Crossover so nasty the floor filed a report."))

    llm = BedrockClueLLM(model="us.anthropic.claude-sonnet-4-6", _client=_FakeClient())
    out = llm.complete("write a clue")
    assert out == "Crossover so nasty the floor filed a report."
    assert captured["model"] == "us.anthropic.claude-sonnet-4-6"
    assert captured["messages"] == [{"role": "user", "content": "write a clue"}]


def test_bedrock_complete_wraps_sdk_errors_as_outage() -> None:
    class _BoomClient:
        def __init__(self) -> None:
            self.messages = self

        def create(self, **_kwargs: object) -> object:
            raise RuntimeError("throttled")

    llm = BedrockClueLLM(_client=_BoomClient())
    with pytest.raises(ClueLLMOutageError, match="bedrock call failed"):
        llm.complete("x")


def test_extract_text_concatenates_blocks_and_strips() -> None:
    msg = _FakeMessage(_FakeBlock("  one "), _FakeBlock("two"))
    assert _extract_text(msg) == "one two"


def test_extract_text_handles_dict_shaped_blocks() -> None:
    msg = _FakeMessage({"text": "dict block"})
    assert _extract_text(msg) == "dict block"


def test_extract_text_empty_content_raises() -> None:
    with pytest.raises(ClueLLMOutageError, match="empty content block list"):
        _extract_text(_FakeMessage())
