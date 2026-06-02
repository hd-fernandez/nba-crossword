"""Clue critic — an LLM quality gate over a finished puzzle's clues.

The clue generator (``nba_mini.clues``) writes one clue per entry, each judged
only by cheap mechanical rules (length, answer-leak). That catches structural
breakage but not the *quality* defects a human reviewer flags: logical gaps
(the clue doesn't lead to its answer), hallucinations (invented nicknames or
arenas), freebies (too easy), broken metaphors, and ordinary fill words given
tortured NBA tie-ins.

This module adds a second pass: one LLM call judges the whole puzzle against
that rubric and returns a per-entry pass/fail with a fix-it reason. The
orchestrator (``generate_clues``) uses those verdicts to regenerate the failing
clues, passing the critic's reason in as guidance, for a bounded number of
rounds. Anything still failing at the end ships anyway (an imperfect clue beats
a missing puzzle) and is logged — matching the "never block shipment"
philosophy already in ``clues.py``.

Design notes:
- The critic reuses the ``ClueLLM`` protocol, so production wires the same
  Bedrock/Anthropic client used for generation, and tests inject a fake.
- The verdict parser is tolerant (strips fences, drops malformed entries) and
  fails *open*: if the critic response can't be parsed, we treat every clue as
  passing rather than block the puzzle. A broken critic must never sink a run.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from nba_mini.clues import ClueLLM, ClueLLMOutageError, GenerationContext
from nba_mini.schema import Entry

logger = logging.getLogger(__name__)

CRITIC_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "critic.md"

VALID_ISSUES = frozenset(
    {
        "logical_gap",
        "hallucination",
        "freebie",
        "broken_metaphor",
        "forced_nba",
        "answer_leak",
        "repetition",
    }
)


@dataclass(frozen=True)
class ClueVerdict:
    """One clue's critic verdict.

    ``passed`` is the only field callers must consult to decide whether to
    regenerate. ``issue`` and ``reason`` are populated on failure and threaded
    into the regeneration prompt as guidance.
    """

    entry_id: str
    passed: bool
    issue: str | None = None
    reason: str | None = None


class CriticError(Exception):
    """Raised for an unrecoverable critic prompt-template problem.

    LLM *outages* surface as ``ClueLLMOutageError`` (reused from clues). A
    malformed *response* never raises — it's handled fail-open in
    ``parse_verdicts`` — so this is reserved for a missing prompt file.
    """


def _load_critic_prompt() -> str:
    try:
        return CRITIC_PROMPT_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise CriticError(f"critic prompt not found at {CRITIC_PROMPT_PATH}") from exc


def _format_clue_table(entries: list[Entry]) -> str:
    """Render entries as ``ID | ANSWER | VOICE | CLUE`` lines for the prompt."""
    return "\n".join(
        f"{e.id} | {e.answer} | {e.voice} | {e.clue}" for e in entries
    )


def _format_reddit(context: GenerationContext) -> str:
    digest = context.reddit_digest
    if digest is None or not digest.posts:
        return "(no discourse)"
    lines: list[str] = []
    for post in digest.posts[:10]:
        flair = f" [{post.flair}]" if post.flair else ""
        lines.append(f"- {post.title}{flair}")
    return "\n".join(lines)


def _format_games(context: GenerationContext) -> str:
    digest = context.games_digest
    if digest is None or not digest.games:
        return "(no games)"
    lines: list[str] = []
    for game in digest.games:
        lines.append(f"- {game.score}")
        for perf in game.top_performers:
            lines.append(f"  - {perf.player} ({perf.team}): {perf.statline}")
    return "\n".join(lines)


def build_critic_prompt(entries: list[Entry], context: GenerationContext) -> str:
    """Assemble the critic prompt for a full set of clued entries."""
    template = _load_critic_prompt()
    return template.format(
        season_context=context.season_context_text.strip(),
        reddit_digest=_format_reddit(context),
        games_digest=_format_games(context),
        clue_table=_format_clue_table(entries),
    )


def parse_verdicts(raw: str, entries: list[Entry]) -> dict[str, ClueVerdict]:
    """Parse the critic's JSON response into a verdict per entry id.

    Fails *open*: any entry the critic didn't return (or returned malformed)
    defaults to a pass, and an entirely unparseable response yields all-pass.
    A flaky critic must never block a puzzle from shipping.
    """
    by_id: dict[str, ClueVerdict] = {
        e.id: ClueVerdict(entry_id=e.id, passed=True) for e in entries
    }

    parsed = _extract_json_array(raw)
    if parsed is None:
        logger.warning("critic response was not parseable JSON; treating all clues as passing")
        return by_id

    valid_ids = {e.id for e in entries}
    for item in parsed:
        if not isinstance(item, dict):
            continue
        entry_id = item.get("id")
        if not isinstance(entry_id, str) or entry_id not in valid_ids:
            continue
        verdict = item.get("verdict")
        if verdict == "fail":
            issue = item.get("issue")
            issue = issue if isinstance(issue, str) and issue in VALID_ISSUES else None
            reason = item.get("reason")
            reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
            by_id[entry_id] = ClueVerdict(
                entry_id=entry_id, passed=False, issue=issue, reason=reason
            )
        # Any non-"fail" verdict (including a malformed one) leaves the default
        # pass in place — fail open.
    return by_id


def _extract_json_array(raw: str) -> list[object] | None:
    """Pull a JSON array out of the model's response. Tolerant of fences/prose."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            loaded = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None

    return loaded if isinstance(loaded, list) else None


def critique_clues(
    entries: list[Entry],
    context: GenerationContext,
    *,
    llm: ClueLLM,
) -> dict[str, ClueVerdict]:
    """Run the critic over a full puzzle's clues. Returns a verdict per entry id.

    ``llm`` must be a client with a token budget large enough for a JSON array
    covering every clue (with fail reasons) — far bigger than the ~256 tokens
    that suffice for a single clue. Use ``build_critic_llm`` (production) or a
    fake (tests); do *not* reuse the generation client, whose small budget
    truncates the critic's response mid-JSON.

    Fails *open* on any LLM outage: a critic that can't be reached returns
    all-pass rather than blocking the run. The caller can still ship.
    """
    if not entries:
        return {}
    prompt = build_critic_prompt(entries, context)
    try:
        raw = llm.complete(prompt)
    except ClueLLMOutageError as exc:
        logger.warning("critic LLM call failed (%s); treating all clues as passing", exc)
        return {e.id: ClueVerdict(entry_id=e.id, passed=True) for e in entries}
    return parse_verdicts(raw, entries)


# Token budget for the critic's JSON verdict array. A puzzle has ~10 clues and
# each failing one carries a one-sentence reason; 2048 leaves generous headroom
# so the response is never truncated mid-JSON (which would fail-open and make
# the gate a silent no-op — the bug this constant exists to prevent).
CRITIC_MAX_TOKENS = 2048


def build_critic_llm(
    *, backend: str, model: str, aws_region: str | None = None
) -> ClueLLM:
    """Build a ClueLLM sized for critic judging (large ``max_tokens``).

    Mirrors the backend selection in ``generate.Deps.production`` but with the
    critic's larger token budget. Lazy on the concrete client classes from
    ``clues`` so the import graph stays one-directional.
    """
    from nba_mini.clues import AnthropicClueLLM, BedrockClueLLM

    if backend == "bedrock":
        return BedrockClueLLM(
            model=model, max_tokens=CRITIC_MAX_TOKENS, aws_region=aws_region
        )
    return AnthropicClueLLM(model=model, max_tokens=CRITIC_MAX_TOKENS)


__all__ = [
    "CRITIC_MAX_TOKENS",
    "ClueVerdict",
    "CriticError",
    "VALID_ISSUES",
    "build_critic_llm",
    "build_critic_prompt",
    "critique_clues",
    "parse_verdicts",
]
