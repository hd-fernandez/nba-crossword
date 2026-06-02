---
title: Fail-open quality gates can become silent no-ops — assert they actually ran
date: 2026-06-02
category: solutions
module: pipeline/nba_mini/critic
problem_type: bug_pattern
component: llm_pipeline
severity: high
applies_when:
  - "A quality gate / validator fails open (treats 'couldn't evaluate' as 'passed')"
  - "An LLM call reuses a client whose token budget was tuned for a different, smaller task"
  - "A gate's effect is invisible unless you inspect its decisions"
tags: [llm, fail-open, quality-gate, max-tokens, json-truncation, observability]
---

# Fail-open gates can silently disable themselves

## Context

We added an LLM "clue critic" that judges a finished puzzle against a rubric and
returns a JSON array of per-clue verdicts; failing clues get regenerated. To be
safe it **fails open**: if the critic response can't be parsed, every clue is
treated as passing (a flaky critic must never block the daily puzzle).

It shipped, tests passed, and a live run logged: *"critic round 1: all clues
passed."* Looked perfect. It was actually doing **nothing.**

The critic reused the generation LLM client, which sets `max_tokens=256` —
correct for one ≤80-char clue, far too small for a JSON array covering ~10
clues with fail reasons. Every critic response was **truncated mid-JSON**,
failed to parse, and fail-open silently rubber-stamped the whole puzzle. The
gate was a no-op from the first commit, and the fail-open design hid it.

## Guidance

**1. A fail-open path must be loud.** Log the *reason* it failed open and make
that line easy to spot. We log `"critic response was not parseable JSON;
treating all clues as passing"` — that line in a live run is what exposed the
bug. Silent fail-open is indistinguishable from "everything genuinely passed."

**2. Never reuse a client's token/size budget across tasks of different output
size.** A budget tuned for output A (one short clue) silently corrupts task B
(a long verdict array). Give the second task its own client:

```python
CRITIC_MAX_TOKENS = 2048           # vs. 256 for a single clue
def build_critic_llm(...): ...     # self-contained, not the generation client
```

Make the consumer *own* its sizing rather than inherit it. We made the critic
protocol self-contained (it carries its own LLM) precisely so a caller can't
accidentally hand it the wrong-sized client.

**3. Verify the gate by its decisions, not its summary.** "All passed" is the
same output whether the gate worked or no-op'd. Confirm it by watching it
*reject* something: our fix was validated by seeing the critic flag a specific
clue (`forced_nba` on AFOOT) and drive a regeneration across rounds. A gate you
haven't seen reject anything is a gate you haven't tested.

## Why This Matters

The combination is the trap: fail-open (good for resilience) + a silent
failure cause (truncation) = a feature that reports success while doing
nothing. Each piece is reasonable alone; together they produce a gate that
passes review, passes tests (fakes return well-formed short JSON, so the
truncation never reproduces in unit tests), and ships dead. Only a live run
with real output sizes — and a log line on the fail-open branch — surfaces it.

## When to Apply

- Any validator/gate/guard that fails open. Add a distinct log line on the
  fail-open branch and grep for it in a real run.
- Any time one LLM client is reused for a second call with a larger expected
  output. Re-check `max_tokens` (and any truncation-prone limit).
- When acceptance-testing a gate, require evidence of a *rejection*, not just
  an overall pass.
