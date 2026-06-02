"""Clue generation for filled grid entries.

Given a list of `Entry` objects with `answer` set (but `clue`/`voice` empty)
and a `GenerationContext` carrying the season snippet and yesterday's
discourse / box scores, this module assigns a voice to each entry per the
50/30/20 wry/discoursey/factual target distribution and prompts an LLM to
write each clue.

The LLM call is hidden behind a tiny `ClueLLM` Protocol so:

1. Tests inject a `FakeClueLLM` and never touch the network.
2. The default `AnthropicClueLLM` lazily imports `anthropic` so this module is
   importable in environments where the SDK isn't installed (the test suite,
   for one, doesn't need it).
3. If we ever swap providers we can do so without touching prompt assembly,
   validation, retry, or the public API.

Validation on every model output:
- ≤160 chars hard (matches `Entry.clue` schema).
- Doesn't contain the answer (case-insensitive substring) — the clue must
  not give the puzzle away.

On validation failure: retry up to `MAX_ATTEMPTS - 1` times with a "previous
clue did X — fix it" addendum baked into the prompt. After exhaustion, fall
back to a templated factual clue derived from a grounding fact (or, lacking
one, a generic answer-shape clue) so we never block puzzle shipment. The
fallback is logged.

A separate failure mode — the LLM call itself raising — is *not* a clue
quality issue; it's an outage. We retry transient errors a small number of
times and then raise `ClueLLMOutageError`. The orchestrator (U8) decides
whether to fail loud or carry on.
"""

from __future__ import annotations

import logging
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from nba_mini.ingest.nba_stats import GamesDigest
from nba_mini.ingest.reddit import RedditDigest, RedditPost
from nba_mini.schema import Entry, Voice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-sonnet-4-5"
"""Default Anthropic model for clue generation.

The plan calls for Sonnet at v0 for cost efficiency. We default to the
current Sonnet release. Callers can override via `GenerationContext.model`.
"""

BEDROCK_DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
"""Default Bedrock inference-profile ID for clue generation.

Bedrock requires a region-prefixed *inference profile* ID (e.g.
``us.anthropic.claude-sonnet-4-6``), not the bare foundation-model ID
(``anthropic.claude-sonnet-4-6``) — on-demand invocation of the bare ID is
rejected. Auth is via the ambient AWS credential chain (SSO profile / env),
so there is no separate API key.
"""

# Voice mix — wry / discoursey / factual = 50 / 30 / 20.
VOICE_TARGETS: tuple[tuple[Voice, float], ...] = (
    ("wry", 0.50),
    ("discoursey", 0.30),
    ("factual", 0.20),
)

# Clue validation budgets.
HARD_LENGTH_LIMIT = 160  # matches Entry.clue Field max_length
SOFT_LENGTH_LIMIT = 80   # warn-only target the prompt asks the model to hit

# Retry budgets.
MAX_ATTEMPTS = 3          # total prompt attempts per entry before fallback
LLM_OUTAGE_RETRIES = 2    # retries on raw LLM exception (in addition to first try)

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_FILES: dict[Voice, str] = {
    "wry": "clue_wry.md",
    "discoursey": "clue_discoursey.md",
    "factual": "clue_factual.md",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ClueGenerationError(Exception):
    """Base class for clue generation failures."""


class ClueLLMOutageError(ClueGenerationError):
    """Raised when the LLM call itself fails repeatedly (network/API outage).

    This is distinct from a "bad clue" outcome — bad clues fall back to a
    templated factual clue. An outage means we couldn't even ask the model;
    the caller decides whether to abort the puzzle or carry on.
    """


class PromptTemplateError(ClueGenerationError):
    """Raised when a prompt markdown file is missing or malformed."""


# ---------------------------------------------------------------------------
# Public models
# ---------------------------------------------------------------------------


class GenerationContext(BaseModel):
    """All the upstream context a clue needs, bundled.

    Keeping this as a pydantic model (rather than a kwarg pile) means we can
    log/serialize it during debugging and that the type contract for the
    orchestrator is explicit.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    season_context_text: str = Field(min_length=1)
    reddit_digest: RedditDigest | None = None
    games_digest: GamesDigest | None = None
    model: str = DEFAULT_MODEL
    seed: int = 0
    """Deterministic seed for voice assignment shuffling."""


# ---------------------------------------------------------------------------
# LLM client abstraction
# ---------------------------------------------------------------------------


class ClueLLM(Protocol):
    """Minimal contract over the LLM call we need.

    `complete(prompt)` returns the model's clue text. Wrapping makes it
    trivial to swap implementations and trivial to fake in tests.
    """

    def complete(self, prompt: str) -> str: ...


@dataclass
class AnthropicClueLLM:
    """Default `ClueLLM` backed by the official `anthropic` SDK.

    Lazy-imports `anthropic` so that test runs (which inject a fake) don't
    require the SDK at import time. The constructor optionally accepts a
    pre-built client for advanced use; otherwise it constructs one on first
    `complete()` call.
    """

    model: str = DEFAULT_MODEL
    max_tokens: int = 256
    api_key: str | None = None
    _client: object | None = None

    def complete(self, prompt: str) -> str:
        client = self._client
        if client is None:
            try:
                import anthropic  # noqa: PLC0415 — lazy on purpose
            except ImportError as exc:
                raise ClueLLMOutageError(
                    "anthropic SDK is not installed; "
                    "install `anthropic>=0.34` or inject a ClueLLM stub"
                ) from exc
            kwargs: dict[str, object] = {}
            if self.api_key is not None:
                kwargs["api_key"] = self.api_key
            client = anthropic.Anthropic(**kwargs)
            self._client = client

        try:
            # Use messages.create for the standard chat surface. We keep the
            # API call minimal — temperature default is fine; we don't need
            # streaming for ≤80-char clues.
            response = client.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — wrap anything raised by SDK
            raise ClueLLMOutageError(f"anthropic call failed: {exc}") from exc

        return _extract_text(response)


@dataclass
class BedrockClueLLM:
    """`ClueLLM` backed by Claude on Amazon Bedrock via `AnthropicBedrock`.

    Identical request/response surface to `AnthropicClueLLM`; the only
    differences are the client class and the auth model. Bedrock authenticates
    with the ambient AWS credential chain (SSO profile, env vars, or instance
    role) rather than an Anthropic API key — so there is nothing key-shaped to
    pass; we just optionally pin the region.

    `model` must be a Bedrock *inference-profile* ID (region-prefixed), e.g.
    ``us.anthropic.claude-sonnet-4-6``. See `BEDROCK_DEFAULT_MODEL`.

    Lazy-imports `anthropic` so test runs that inject a fake never need the SDK.
    """

    model: str = BEDROCK_DEFAULT_MODEL
    max_tokens: int = 256
    aws_region: str | None = None
    _client: object | None = None

    def complete(self, prompt: str) -> str:
        client = self._client
        if client is None:
            try:
                import anthropic  # noqa: PLC0415 — lazy on purpose
            except ImportError as exc:
                raise ClueLLMOutageError(
                    "anthropic SDK is not installed; "
                    "install `anthropic>=0.34` or inject a ClueLLM stub"
                ) from exc
            kwargs: dict[str, object] = {}
            if self.aws_region is not None:
                kwargs["aws_region"] = self.aws_region
            client = anthropic.AnthropicBedrock(**kwargs)
            self._client = client

        try:
            response = client.messages.create(  # type: ignore[attr-defined]
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # noqa: BLE001 — wrap anything raised by SDK
            raise ClueLLMOutageError(f"bedrock call failed: {exc}") from exc

        return _extract_text(response)


def _extract_text(response: object) -> str:
    """Pull concatenated text out of an Anthropic `Message`.

    Shared by the direct-API and Bedrock clients — both return the same
    `Message` shape with a `.content` list of content blocks. We expect text
    blocks; objects expose `.text`, older/dict shapes use `["text"]`.
    """
    try:
        content = response.content  # type: ignore[attr-defined]
        text_parts: list[str] = []
        for block in content:
            t = getattr(block, "text", None)
            if t is None and isinstance(block, dict):
                t = block.get("text")
            if t:
                text_parts.append(str(t))
        if not text_parts:
            raise ClueLLMOutageError("model returned an empty content block list")
        return "".join(text_parts).strip()
    except ClueLLMOutageError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ClueLLMOutageError(f"model returned unexpected shape: {exc}") from exc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_clues(
    entries: list[Entry],
    context: GenerationContext,
    *,
    llm: ClueLLM | None = None,
) -> list[Entry]:
    """Generate a clue + assign a voice for each entry.

    Args:
        entries: The filled-grid entries (answer already populated). The
            `clue` field on input is treated as a placeholder and overwritten;
            same for `voice`.
        context: Season snippet + upstream digests + model choice.
        llm: Optional injected LLM client. Tests pass a `FakeClueLLM`. If
            omitted, the default `AnthropicClueLLM(model=context.model)` is
            built and used.

    Returns:
        A new list of `Entry` with `clue` and `voice` populated. Length and
        order match the input list. The original entries are not mutated.

    Raises:
        ClueLLMOutageError: if the underlying LLM call repeatedly raises for
            a single entry, even after our retry budget. We bubble out
            instead of falling back, because a persistent outage means the
            *next* entry will also fail and we should fail the run loud.
    """
    if not entries:
        return []

    chosen_llm: ClueLLM = llm or AnthropicClueLLM(model=context.model)

    voices = _assign_voices(len(entries), seed=context.seed)
    out: list[Entry] = []
    # Accumulate the clues we've already written so each new clue can be told
    # to pick a *different* angle. This is what stops every clue in a puzzle
    # from reaching for the same salient storyline (the "thobe ×4" problem):
    # clues are generated sequentially and each sees its predecessors.
    prior: list[tuple[str, str]] = []  # (answer, clue) in generation order
    for entry, voice in zip(entries, voices, strict=True):
        clue = _generate_one_clue(entry, voice, context, chosen_llm, prior_clues=prior)
        out.append(entry.model_copy(update={"clue": clue, "voice": voice}))
        prior.append((entry.answer, clue))
    return out


# ---------------------------------------------------------------------------
# Voice assignment
# ---------------------------------------------------------------------------


def _assign_voices(n: int, *, seed: int) -> list[Voice]:
    """Return a length-`n` list of voices approximating the 50/30/20 mix.

    Strategy: compute integer counts via largest-remainder rounding, build
    a deterministic shuffled sequence so the voice order doesn't always put
    all wries first.
    """
    if n <= 0:
        return []

    raw = [(voice, target * n) for voice, target in VOICE_TARGETS]
    counts = {voice: int(amount) for voice, amount in raw}
    remainders = sorted(
        ((amount - int(amount), voice) for voice, amount in raw),
        reverse=True,
    )
    leftover = n - sum(counts.values())
    for _, voice in remainders[:leftover]:
        counts[voice] += 1

    # Edge case for n=1: 50/30/20 → 0/0/0 + 1 leftover → wry. That's the
    # right call for a 1-entry puzzle (which won't happen in practice but
    # the math should still hold).
    sequence: list[Voice] = []
    for voice, _ in VOICE_TARGETS:
        sequence.extend([voice] * counts[voice])

    rng = random.Random(seed)
    rng.shuffle(sequence)
    return sequence


# ---------------------------------------------------------------------------
# Per-entry generation
# ---------------------------------------------------------------------------


def _generate_one_clue(
    entry: Entry,
    voice: Voice,
    context: GenerationContext,
    llm: ClueLLM,
    *,
    prior_clues: list[tuple[str, str]] | None = None,
) -> str:
    """Run the prompt-validate-retry loop for a single entry. Always returns a clue.

    Outage of the LLM itself bubbles out as `ClueLLMOutageError`. Bad clue
    content (length / contains-answer) cycles into a retry; after exhausting
    `MAX_ATTEMPTS`, we return a templated fallback so the puzzle ships.

    ``prior_clues`` is the list of ``(answer, clue)`` pairs already written for
    this puzzle, in order. It's rendered into the prompt so the model can pick a
    distinct angle and avoid repeating a storyline across the puzzle.
    """
    template = _load_prompt_template(voice)
    discourse_slice = _slice_discourse_for_entry(entry, context.reddit_digest)
    grounding_fact = _grounding_fact_for_entry(entry, context.games_digest)
    prior_block = _format_prior_clues(prior_clues)

    last_attempt: str | None = None
    last_reason: str | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_note = _format_retry_note(last_attempt, last_reason)
        prompt = template.format(
            season_context=context.season_context_text.strip(),
            discourse_slice=discourse_slice or "(no specific discourse anchor for this entry)",
            grounding_fact=grounding_fact or "(none)",
            prior_clues=prior_block,
            answer=entry.answer,
            retry_note=retry_note,
        )

        try:
            raw = _call_llm_with_retry(llm, prompt)
        except ClueLLMOutageError:
            raise

        clue = _normalize_clue(raw)
        ok, reason = _validate_clue(clue, entry.answer)
        if ok:
            if len(clue) > SOFT_LENGTH_LIMIT:
                logger.warning(
                    "clue for %s exceeds soft length limit (%d > %d)",
                    entry.id,
                    len(clue),
                    SOFT_LENGTH_LIMIT,
                )
            return clue

        logger.info(
            "clue for %s rejected on attempt %d: %s (clue=%r)",
            entry.id,
            attempt,
            reason,
            clue,
        )
        last_attempt = clue
        last_reason = reason

    # All attempts exhausted; fall back to a templated factual clue.
    fallback = _fallback_clue(entry, grounding_fact)
    logger.warning(
        "clue generation for %s exhausted retries; using fallback clue %r",
        entry.id,
        fallback,
    )
    return fallback


def _call_llm_with_retry(llm: ClueLLM, prompt: str) -> str:
    """Wrap the raw LLM call with a tiny retry budget for transient outages."""
    last_exc: Exception | None = None
    for attempt in range(LLM_OUTAGE_RETRIES + 1):
        try:
            return llm.complete(prompt)
        except ClueLLMOutageError as exc:
            last_exc = exc
            if attempt < LLM_OUTAGE_RETRIES:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1,
                    LLM_OUTAGE_RETRIES + 1,
                    exc,
                )
                continue
            break
        except Exception as exc:  # noqa: BLE001 — coerce unknowns into typed
            last_exc = ClueLLMOutageError(f"unexpected LLM error: {exc}")
            if attempt < LLM_OUTAGE_RETRIES:
                logger.warning(
                    "LLM call failed (attempt %d/%d): %s",
                    attempt + 1,
                    LLM_OUTAGE_RETRIES + 1,
                    exc,
                )
                continue
            break
    assert last_exc is not None
    if isinstance(last_exc, ClueLLMOutageError):
        raise last_exc
    raise ClueLLMOutageError(str(last_exc)) from last_exc


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_clue(clue: str, answer: str) -> tuple[bool, str | None]:
    """Return (ok, reason). `reason` is None on success."""
    if not clue:
        return False, "empty clue"
    if len(clue) > HARD_LENGTH_LIMIT:
        return (
            False,
            f"too long ({len(clue)} chars; must be <= {HARD_LENGTH_LIMIT})",
        )
    if answer.lower() in clue.lower():
        return False, f"contains the answer {answer!r} as a substring"
    return True, None


def _normalize_clue(raw: str) -> str:
    """Strip the kinds of decoration models often add unprompted.

    - Surrounding whitespace.
    - Surrounding straight or curly quotes.
    - A leading "Clue:" / "Answer:" label.
    - Trailing markdown emphasis.
    """
    s = raw.strip()
    # Strip leading "Clue:" / "Answer:" labels (case-insensitive).
    s = re.sub(r"^(clue|answer)\s*:\s*", "", s, flags=re.IGNORECASE)
    # Strip surrounding quote pairs (one set).
    if len(s) >= 2:
        for opener, closer in (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’")):
            if s.startswith(opener) and s.endswith(closer):
                s = s[1:-1].strip()
                break
    # If the model wrapped its response in markdown emphasis, peel one layer.
    if s.startswith("**") and s.endswith("**") and len(s) > 4:
        s = s[2:-2].strip()
    return s


# ---------------------------------------------------------------------------
# Prompt assembly helpers
# ---------------------------------------------------------------------------


def _load_prompt_template(voice: Voice) -> str:
    """Read the markdown template for a voice. Cached at module import time would
    be premature optimization here; six entries × three voices is cheap."""
    name = PROMPT_FILES[voice]
    path = PROMPTS_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptTemplateError(f"prompt file not found: {path}") from exc


def _format_prior_clues(prior_clues: list[tuple[str, str]] | None) -> str:
    """Render the already-written clues as a bullet list for the prompt.

    The clue-writer uses this to avoid repeating an angle across the puzzle.
    We deliberately *do* show the prior answers — they're already visible in
    the solved puzzle, so there's no leak — alongside each clue, so the model
    can see which storylines are spent. Returns a neutral placeholder when this
    is the first clue (or when prior clues aren't being threaded through).
    """
    if not prior_clues:
        return "(none yet — this is the first clue in the puzzle)"
    return "\n".join(f"- {answer}: {clue}" for answer, clue in prior_clues)


def _format_retry_note(prev: str | None, reason: str | None) -> str:
    if prev is None or reason is None:
        return ""
    return (
        "## Retry note\n\n"
        f"Your previous attempt was rejected because it {reason}.\n"
        f"Previous attempt: {prev!r}\n"
        "Please write a new clue that fixes that specific problem.\n"
    )


def _slice_discourse_for_entry(entry: Entry, digest: RedditDigest | None) -> str:
    """Return a short slice of the reddit digest relevant to this entry's answer.

    The match is loose on purpose: substring of the answer in title or comment
    body. For v0 this is good enough to give the model *something* to anchor
    on; the v0.5 ranker can do better.
    """
    if digest is None or not digest.posts:
        return ""

    needle = entry.answer.lower()
    chunks: list[str] = []
    for post in digest.posts:
        if _post_relevant_to(post, needle):
            chunks.append(_format_post_for_prompt(post))
    if not chunks:
        # Always include at least 2 top posts so the model has *some* feel
        # for yesterday's vibe even if there's no exact answer match.
        for post in digest.posts[:2]:
            chunks.append(_format_post_for_prompt(post))
    return "\n\n".join(chunks)


def _post_relevant_to(post: RedditPost, needle: str) -> bool:
    if needle in post.title.lower():
        return True
    return any(needle in c.lower() for c in post.top_comments)


def _format_post_for_prompt(post: RedditPost) -> str:
    """A compact, prompt-friendly serialization of one reddit post."""
    flair = f" [{post.flair}]" if post.flair else ""
    head = f"- {post.title}{flair} (score {post.score})"
    if not post.top_comments:
        return head
    bullets = "\n".join(f"  - {c}" for c in post.top_comments[:3])
    return f"{head}\n{bullets}"


def _grounding_fact_for_entry(entry: Entry, digest: GamesDigest | None) -> str | None:
    """A single short fact pulled from the box scores, if anything matches."""
    if digest is None or not digest.games:
        return None

    needle = entry.answer.lower()
    for game in digest.games:
        if needle in game.home.lower() or needle in game.away.lower():
            return f"{game.score}."
        for performer in game.top_performers:
            if needle in performer.player.lower():
                return f"{performer.player} ({performer.team}): {performer.statline}."
    return None


# ---------------------------------------------------------------------------
# Fallback clue
# ---------------------------------------------------------------------------


def _fallback_clue(entry: Entry, grounding_fact: str | None) -> str:
    """A templated factual clue used when the LLM can't produce a valid one.

    We never block puzzle shipment on clue quality; an ugly clue is better
    than a missing one. The fallback is deliberately bland — it tells you
    something true about the answer's shape without giving it away — and the
    pipeline logs every fallback so we can audit how often this fires.
    """
    if grounding_fact:
        candidate = f"Box-score line: {grounding_fact}"
        # Ensure the fallback itself doesn't smuggle the answer or run too long.
        if (
            entry.answer.lower() not in candidate.lower()
            and len(candidate) <= HARD_LENGTH_LIMIT
        ):
            return candidate
    n = len(entry.answer)
    return f"NBA-related answer ({n} letters); see today's discourse."


__all__ = [
    "AnthropicClueLLM",
    "BedrockClueLLM",
    "BEDROCK_DEFAULT_MODEL",
    "ClueGenerationError",
    "ClueLLM",
    "ClueLLMOutageError",
    "DEFAULT_MODEL",
    "GenerationContext",
    "HARD_LENGTH_LIMIT",
    "MAX_ATTEMPTS",
    "PromptTemplateError",
    "SOFT_LENGTH_LIMIT",
    "VOICE_TARGETS",
    "generate_clues",
]
