---
title: Adding a constraint to a backtracking fill — reject-in-place vs. retry-the-seed
date: 2026-06-02
category: solutions
module: pipeline/nba_mini/grid
problem_type: architecture_pattern
component: algorithm
severity: medium
applies_when:
  - "Adding a new validity constraint to a backtracking/constraint-satisfaction search"
  - "A 'just reject the bad output' fix starts failing far more cases than expected"
  - "The search space is already tight (thin wordlist, small grid, few templates)"
tags: [backtracking, constraint-satisfaction, grid-fill, feasibility, determinism]
---

# Backtracker constraints: reject-in-place vs. retry-the-seed

## Context

The 5×5 grid fill is a seeded backtracking search: place candidates, then
complete the remaining slots from a wordlist, backtracking on dead ends. In one
session we added **two** new quality constraints to it, and they needed
*opposite* implementations — which is the lesson.

1. **No junk crossings** (a fully-crossed slot must spell a real word). Fix:
   reject in place — `if pattern not in valid: return False`. This works great:
   the rejected node has unfilled sibling slots the backtracker can re-fill
   differently, so the search routes around it. Fill success stayed ~100%.

2. **No duplicate answers** (same word can't appear twice in one grid). The
   instinct was identical — `if pattern in used: return False`. It failed
   **~100% of grids.** Reverted immediately on measurement.

## Why the same-looking fix behaved oppositely

A reject-in-place constraint only works if the backtracker has **freedom to
satisfy it** near the rejection point. The junk-crossing reject fires while
slots are still open, so there's room to maneuver. The duplicate reject fires
on a slot that's *already fully determined by its crossings* — to avoid the
duplicate you'd have to change a word two or three slots away, which this
single-pass, most-constrained-first backtracker won't reorganize. Against a
thin wordlist (few options per slot) the constraint just turns almost every
terminal node into a dead end, and the whole grid fails.

Rule of thumb: **a constraint local to the current decision can be rejected
in place; a constraint that's only knowable after distant decisions are locked
in cannot — it starves the search.**

## Guidance

For the "knowable only at the end / over-constrains the search" case, don't
fight the backtracker. Generate a full solution and **retry with a different
seed**, preferring a clean one:

```python
first = None
for attempt in range(RETRY_SEEDS):
    grid = fill_with_seed(..., seed=seed + attempt)
    if grid is None:
        continue
    first = first or grid
    if not has_violation(grid):          # cheap post-hoc check
        return grid
return first    # fall back: a rare violation beats no output at all
```

This keeps three properties that matter:

- **Feasibility:** never lowers the fill rate — worst case you ship the first
  valid grid, exactly as before.
- **Determinism:** same inputs + same starting seed → same seed sequence →
  same result. (Don't use wall-clock or RNG for the retry offset.)
- **Graceful degradation:** matches the project's "an imperfect artifact beats
  a missing one" philosophy — log the fallback, don't raise.

## Why This Matters

"Just reject the invalid output" is the reflex when adding a constraint to a
search, and it's right often enough to be a trap. The cost of guessing wrong is
invisible in a unit test that fills one grid and silent in a code review — it
only shows up when you measure the fill rate across many seeds. **Always
measure success rate across a seed sweep after adding a constraint to a
backtracker**, not just "does seed 0 still work."

Cost paid: the seed-retry does up to `RETRY_SEEDS` full fills per call, and a
stacked constraint (real-word guard) already slowed each fill — so the grid
test suite went from seconds to minutes. Acceptable for a once-a-day pipeline;
worth memoizing or shrinking seed ranges if it becomes a dev-loop drag.

## When to Apply

- Adding any global/whole-solution constraint to a local backtracking search.
- When a reject-in-place constraint tanks the success rate: switch to
  generate-and-retry before weakening the constraint or rewriting the search.
- Conversely, don't reach for retry when reject-in-place works (the junk-
  crossing guard) — retry is strictly more expensive.
