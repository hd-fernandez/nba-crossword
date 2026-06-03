# nba-crossword Working Instructions

A daily NBA-themed mini crossword app. Clues refresh nightly from the previous day's NBA slate.

## Context-engineering artifact paths

The compound-engineering plugin skills (`ce-plan`, `ce-brainstorm`, `ce-code-review`, `ce-compound`, `ce-doc-review`, and related) reference `docs/plans/`, `docs/brainstorms/`, `docs/reviews/`, `docs/solutions/` as defaults. In this project, those paths are overridden. Always substitute:

| Skill default | This project |
| --- | --- |
| `docs/plans/` | `compound-engineering/plans/` |
| `docs/brainstorms/` | `compound-engineering/brainstorms/` |
| `docs/reviews/` | `compound-engineering/reviews/` |
| `docs/solutions/` | `compound-engineering/solutions/` |

Do NOT create a `docs/` folder at the repo root.

Project-specific artifact paths (no skill equivalent):

- Reference snapshots: `compound-engineering/reference/`
- Templates: `compound-engineering/templates/`
- Analyses: `compound-engineering/analyses/`
- Todos: `compound-engineering/todos/`

`compound-engineering/solutions/` is a searchable store of documented learnings
from past problems (bugs, root-cause diagnoses, conventions, workflow patterns),
each with YAML frontmatter (`module`, `problem_type`, `tags`). Relevant when
implementing or debugging in an area that's been worked before — a quick grep
there can surface a prior diagnosis (e.g. grid-fill, ingest, the clue critic).

## How to Work

- Read existing code before changing it.
- Make a plan first; don't code immediately unless explicitly asked.
- Prefer small, safe, reviewable changes.
- Commit often.

## Project Rules

### Puzzle content — keep it basketball
- The puzzle must read as a **basketball** puzzle: lean toward NBA/WNBA **answers** AND basketball-aware **clues**, not just one good NBA answer surrounded by generic fill. (Round-1's "don't force basketball on fill words" over-corrected — see round-2 markup in `compound-engineering/analyses/2026-06-02-clue-rating-batch-round2.md`.)
- Non-basketball answers are fine **if the clue is basketball-aware** (the WNBA `AWAKE` → "not sleeping on [player]'s triple-double" pattern is the bar). A clean non-NBA fill clue is the *floor* of acceptable, not the target.
- No factual misses in clues. The critic must catch these — two that slipped through round 2: claiming a team lacked home court when it had it; pluralization mismatches (clue for a singular when the answer is plural).

### Grid fill (`pipeline/nba_mini/grid.py`)
- The fill reliably seats **1 candidate (basketball) answer** per grid against the current v0 wordlist. Seating **2+** is gated by **wordlist richness**, not the fill algorithm — verified 2026-06-03: even a trivial pool like `[STEAL, BLOCK]` cannot cross both into the 4-corner template at a 200k-step budget, because the thin wordlist can't thread real words around two forced answers. The deferred **frequency-filtered wordlist expansion** is the real lever; backtracker tuning is not. (A 466-line iterative-deepening rewrite was tried and reverted — it added no seating gain and pushed worst-case latency to ~30s.)
- A single `fill_grid` call taking **10–20s is acceptable** (once-daily pipeline). Don't sacrifice correctness (real-words-only, no duplicate answers, distinct grids per date) to shave seconds.
- Distinct grids per date come from distinct **inputs** (per-date seed + per-date candidate pool), not from seating more candidates. "Identical grids" is an input-sameness symptom, not a fill-algorithm one.

### Performance posture
- This is a once-a-day batch pipeline. Favor correctness and content quality over latency everywhere unless a step becomes a genuine dev-loop drag.
