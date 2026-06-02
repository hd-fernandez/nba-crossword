"""Tests for the clue critic quality gate. Never hits a real LLM endpoint.

Coverage:
- Prompt assembly includes the clue table and material.
- Verdict parsing: pass, fail-with-issue, fenced JSON, malformed → fail open.
- critique_clues fails open on an LLM outage.
- Integration: generate_clues(critic=...) regenerates a failing clue using the
  critic's note, and ships-and-logs a clue that never passes.
"""

from __future__ import annotations

from typing import Callable

from nba_mini.clues import GenerationContext, generate_clues
from nba_mini.critic import (
    ClueVerdict,
    build_critic_prompt,
    critique_clues,
    parse_verdicts,
)
from nba_mini.schema import Entry


class FakeClueLLM:
    def __init__(self, responder: Callable[[str], str]) -> None:
        self.responder = responder
        self.calls: list[str] = []

    def complete(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self.responder(prompt)


class BoomLLM:
    """A ClueLLM that always raises the typed outage error."""

    def complete(self, prompt: str) -> str:
        from nba_mini.clues import ClueLLMOutageError

        raise ClueLLMOutageError("simulated outage")


def _entry(id: str, answer: str, clue: str = "A clue.", voice: str = "factual") -> Entry:
    return Entry(
        id=id,
        direction="across",  # type: ignore[arg-type]
        row=0,
        col=0,
        answer=answer,
        clue=clue,
        voice=voice,  # type: ignore[arg-type]
    )


def _ctx() -> GenerationContext:
    return GenerationContext(
        season_context_text="NBA Conference Semifinals, late May 2026.",
        seed=0,
    )


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------


def test_build_critic_prompt_includes_clue_table_and_context() -> None:
    entries = [_entry("1A", "WEMBY", "Spurs center, recent ejection."),
               _entry("2D", "ADOBE", "Sun-dried brick.")]
    prompt = build_critic_prompt(entries, _ctx())
    assert "1A | WEMBY | factual | Spurs center, recent ejection." in prompt
    assert "2D | ADOBE | factual | Sun-dried brick." in prompt
    assert "Semifinals" in prompt  # season context funneled in


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------


def test_parse_verdicts_pass_and_fail() -> None:
    entries = [_entry("1A", "WEMBY"), _entry("2D", "ADOBE")]
    raw = (
        '[{"id": "1A", "verdict": "pass"}, '
        '{"id": "2D", "verdict": "fail", "issue": "forced_nba", '
        '"reason": "Clue it as a brick, not an arena."}]'
    )
    verdicts = parse_verdicts(raw, entries)
    assert verdicts["1A"].passed is True
    assert verdicts["2D"].passed is False
    assert verdicts["2D"].issue == "forced_nba"
    assert "brick" in verdicts["2D"].reason


def test_parse_verdicts_tolerates_code_fence() -> None:
    entries = [_entry("1A", "WEMBY")]
    raw = '```json\n[{"id": "1A", "verdict": "pass"}]\n```'
    verdicts = parse_verdicts(raw, entries)
    assert verdicts["1A"].passed is True


def test_parse_verdicts_unknown_issue_is_dropped_but_still_fails() -> None:
    entries = [_entry("1A", "WEMBY")]
    raw = '[{"id": "1A", "verdict": "fail", "issue": "not_a_real_issue", "reason": "x"}]'
    verdicts = parse_verdicts(raw, entries)
    assert verdicts["1A"].passed is False
    assert verdicts["1A"].issue is None  # unknown issue scrubbed
    assert verdicts["1A"].reason == "x"


def test_parse_verdicts_fails_open_on_garbage() -> None:
    entries = [_entry("1A", "WEMBY"), _entry("2D", "ADOBE")]
    verdicts = parse_verdicts("not json at all", entries)
    # Unparseable → every clue treated as passing.
    assert all(v.passed for v in verdicts.values())
    assert set(verdicts) == {"1A", "2D"}


def test_parse_verdicts_missing_entry_defaults_to_pass() -> None:
    entries = [_entry("1A", "WEMBY"), _entry("2D", "ADOBE")]
    raw = '[{"id": "1A", "verdict": "fail", "issue": "freebie", "reason": "too easy"}]'
    verdicts = parse_verdicts(raw, entries)
    assert verdicts["1A"].passed is False
    # 2D wasn't mentioned → default pass, never blocks.
    assert verdicts["2D"].passed is True


# ---------------------------------------------------------------------------
# critique_clues fail-open
# ---------------------------------------------------------------------------


def test_critique_clues_fails_open_on_outage() -> None:
    entries = [_entry("1A", "WEMBY"), _entry("2D", "ADOBE")]
    verdicts = critique_clues(entries, _ctx(), llm=BoomLLM())
    assert all(v.passed for v in verdicts.values())


def test_critique_clues_empty_entries() -> None:
    assert critique_clues([], _ctx(), llm=BoomLLM()) == {}


# ---------------------------------------------------------------------------
# Integration with generate_clues
# ---------------------------------------------------------------------------


def test_generate_clues_regenerates_failing_clue_then_passes() -> None:
    """A clue that fails round 1 is regenerated; round 2 passes → kept."""
    # Generation LLM: returns a marker so we can see the regen happened.
    gen_calls = {"n": 0}

    def gen_responder(prompt: str) -> str:
        gen_calls["n"] += 1
        # If this is a regeneration (critic note present), return a "fixed" clue.
        if "editor reviewed" in prompt:
            return "A fixed clue."
        return "An original clue."

    gen_llm = FakeClueLLM(gen_responder)

    entries = [_entry("1A", "ADOBE", clue="ph", voice="factual")]

    # Critic: fail on round 1 (clue == original), pass once it's fixed.
    def fake_critic(ents, context):
        clue = ents[0].clue
        if clue == "A fixed clue.":
            return {"1A": ClueVerdict("1A", passed=True)}
        return {
            "1A": ClueVerdict(
                "1A", passed=False, issue="forced_nba", reason="Clue it as a brick."
            )
        }

    out = generate_clues(entries, _ctx(), llm=gen_llm, critic=fake_critic)
    assert out[0].clue == "A fixed clue."


def test_generate_clues_ships_clue_that_never_passes() -> None:
    """If the critic always fails a clue, we still ship the best attempt."""

    def gen_responder(prompt: str) -> str:
        return "Stubborn clue."

    gen_llm = FakeClueLLM(gen_responder)
    entries = [_entry("1A", "ADOBE", clue="ph")]

    def always_fail_critic(ents, context):
        return {"1A": ClueVerdict("1A", passed=False, issue="freebie", reason="too easy")}

    out = generate_clues(entries, _ctx(), llm=gen_llm, critic=always_fail_critic)
    # Never raises, always returns a clue.
    assert out[0].clue == "Stubborn clue."
    assert len(out) == 1


def test_generate_clues_without_critic_is_single_pass() -> None:
    """Default (no critic) behavior is unchanged: no extra judging calls."""

    def gen_responder(prompt: str) -> str:
        assert "editor reviewed" not in prompt  # never regenerated
        return "A clue."

    gen_llm = FakeClueLLM(gen_responder)
    entries = [_entry("1A", "WEMBY")]
    out = generate_clues(entries, _ctx(), llm=gen_llm)  # no critic=
    assert out[0].clue == "A clue."
