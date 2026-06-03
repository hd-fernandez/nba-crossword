---
title: "Identical daily grids: one template, not seeding or inputs"
date: 2026-06-03
category: solutions
module: pipeline/nba_mini/grid
problem_type: logic_error
component: algorithm
symptoms:
  - "4 of 5 consecutive dates produce a byte-identical filled grid"
  - "Changing the seed barely changes the output"
  - "Two puzzles from different dates look like copies of each other"
root_cause: logic_error
resolution_type: code_fix
severity: medium
tags: [grid-fill, templates, determinism, variety, diagnosis]
---

# Identical daily grids trace to a single template, not the seed

## Problem

Reviewers flagged that the daily puzzle for different dates looked identical
("Grid A and Grid B look the same"). The grid fill is seeded off the publish
date (`seed = target_date.toordinal()`), so distinct dates get distinct seeds —
yet the output collapsed to the same grid most days.

## Symptoms

- 4 of 5 consecutive date-seeds produced a byte-identical answer grid
  (`SPAYARDSAFOOTWEMBYROE`).
- Bumping the seed by ±1 (adjacent dates) usually changed nothing.

## What Didn't Work

- **First (wrong) diagnosis: "input sameness."** It's tempting to blame the same
  dominant candidate (WEMBY) being fed each day. That's a contributor but not the
  root — even with a fixed pool, *different seeds should diverge.* They didn't.
- **Alternating `black_squares` (2 vs 4) by date.** This raised distinctness
  (2/5 → 5/7) but the 2-block templates seat **zero** candidate answers (verified:
  WEMBY only seats on the 4-block layout). That trades away the basketball
  content the puzzle exists for — a bad fix.

## Solution

Root cause: **`black_squares=4` has exactly one registered template** (the
4-corner layout). With one fixed black-square pattern + a dominant 5-letter
candidate pinned into the same slot + a deterministic most-constrained-first
fill, adjacent seeds converge on the same completion. The seed had almost
nothing to vary.

The correct fix is a **second clean 4-block template** that still exposes four
length-5 slots (so a 5-letter answer like WEMBY still seats), letting the
existing seed-rotation (`templates[seed % len]`) alternate layouts so
consecutive days look structurally different. This is deferred grid/wordlist
work, captured here so it isn't re-diagnosed from scratch. (A richer,
frequency-filtered wordlist is the other lever: it would let the 2-block
templates carry basketball answers too.)

## Why This Works

Variety in a deterministic fill comes from the *structure* the seed selects
among, not from the seed alone. One template = one structure = the seed can only
reshuffle wordlist fill around fixed candidate slots, which a thin wordlist
barely does. Add a second equally-capable template and the seed has a real fork
to take.

## Prevention

- When a seeded generator produces near-identical outputs, **count the
  structures it actually chooses among** before blaming the seed or the inputs.
  Here: `len(_TEMPLATES_BY_BLOCK_COUNT[4]) == 1` was the whole story.
- Don't "fix" variety by switching to a structure that drops the content you
  care about — verify the alternative still seats candidates first
  (see [[2026-06-03-verify-before-you-claim]]).
- The lever for *more* basketball answers is wordlist richness, not backtracker
  tuning (recorded in project `CLAUDE.md`).

## Related Issues

- [[2026-06-02-backtracker-constraint-feasibility]] — same fill, constraint-placement lesson
- [[2026-06-03-verify-before-you-claim]] — the seed-sweep that disproved the input-sameness theory
