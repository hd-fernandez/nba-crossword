---
title: Verify before you claim — seed-sweep your fix, distrust suspicious counts
date: 2026-06-03
category: solutions
module: pipeline/nba_mini
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "About to record a 'fixed' or 'now does N' claim about a stochastic/seeded algorithm"
  - "A measured count or metric smells wrong (too low, too round, too convenient)"
  - "Continuing a fix the next day from notes rather than from a fresh measurement"
tags: [verification, measurement, determinism, grid-fill, ingest, false-fix]
---

# Verify before you claim

## Context

Two incidents in the same project, same root habit: trusting a claim instead of
measuring it.

**Incident A — the "seats 2" false fix.** An end-of-day note recorded that a
466-line iterative-deepening rewrite of the grid backtracker "now seats 2
candidate answers + distinct grids." The next morning a seed-sweep showed it
seated **1** on every pool tried (including the trivial `[STEAL, BLOCK]`),
*same as the simpler committed baseline*, while pushing worst-case fill latency
from ~16s to ~30s. The "seats 2" claim had never been run — it was aspirational.
The rewrite was reverted; the simpler code kept.

**Incident B — "119 posts."** A pipeline log reported only 119 Reddit posts
across 7 days of NBA subreddits. The instinct "that can't be right" was correct:
`grep -c "<entry>"` returned a wrong count because the RSS is single-line XML,
and separately the feed was capped at Reddit's default `limit=25`/sub. Fixing
both lifted the real pool to ~549 posts.

## Guidance

**1. A "fixed" / "now does N" claim about a seeded or stochastic algorithm is not
real until you've run a seed sweep.** One run proves nothing; the win (or its
absence) only shows across many seeds. For the grid that meant:

```python
# The minimum bar before claiming "seats N":
for seed in range(8):
    g = fill_grid(pool, wordlist, seed=seed)
    seated = [w for w in answers(g) if w in set(pool)]
    print(seed, len(seated), seated)   # is it N on most/all seeds? and how slow?
```

If you can't show the sweep output, you don't have the result.

**2. When you can't beat a baseline, measure the baseline too.** The rewrite
looked plausible in isolation. Running the *old* code on the same pool showed it
already did just as well — which turned a "ship it" into a "revert it."

**3. A suspicious number is a lead, not a nuisance.** "Only 119?" was right.
Before trusting any count, confirm the *measurement* (here: `grep -c` on
single-line XML undercounts — use `grep -oc` or parse the XML) AND the *source
limit* (here: an unstated API default cap).

**4. Resume from a measurement, not from yesterday's note.** Notes written at the
end of a long session can encode an unverified hope. Re-measure before building
on them.

## Why This Matters

The false "seats 2" note nearly shipped a slower, more complex algorithm that
delivered no gain — and would have stood as documented "fact" for the next
person. The cost of the seed sweep is seconds; the cost of a wrong claim
compounds. "Diagnosed structural" is not "fix verified," and "the log says N" is
not "N is true."

## When to Apply

- Before writing any "this now does X" claim about grid fill or any seeded search
- Before trusting a count/metric from a log, especially one that feels off
- When picking a fix up from prior-session notes

## Examples

- **Before:** note says "rewrite seats 2." → **After:** seed-sweep shows 1 on
  all 8 seeds + 30s worst case → revert, keep the simpler code.
- **Before:** "119 posts, I guess that's all there is." → **After:** `grep -oc`
  shows 25/sub (a cap), real ceiling 100/sub → pool ~549.

## Related

- [[2026-06-02-backtracker-constraint-feasibility]] — measure-then-decide on the same grid fill
- [[2026-06-02-fail-open-silent-noop]] — another "looked like it worked, wasn't" gate
