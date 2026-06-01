---
title: Isolate independent tasks in a CI cron so one failure doesn't drop the others
date: 2026-06-01
category: solutions
module: .github/workflows/daily-puzzle
problem_type: bug_pattern
component: ci_cd
severity: high
applies_when:
  - "A scheduled CI job generates/publishes several independent artifacts in one run"
  - "A bash loop or sequential steps run under set -e and any one can fail transiently"
tags: [github-actions, cron, set-e, failure-isolation, batch]
---

# Per-task isolation in a CI cron

## Context

The daily job generates four independent artifacts: NBA crossword, WNBA
crossword, NBA Bee, WNBA Bee. They were produced by a `for league in nba wnba`
loop under `set -euo pipefail`, followed by a separate Bee step, then a commit
step. A code review constructed the failure: a single transient NBA failure
(Bedrock blip, nba.com 5xx) returns exit 1, `set -e` aborts the step
**before WNBA runs**, and because the step failed, the later Bee step and the
commit step never run either. One NBA hiccup drops three unrelated artifacts —
including the corpus-only Bees that don't even depend on the thing that failed.

The comment in the workflow literally claimed "an off-day for one league
doesn't block the other," which the control flow contradicted.

## Guidance

**Isolate each independent unit; aggregate the failure at the end.** Drop `-e`
for the loop, track failures, keep going, then fail the step once at the end so
the run still goes red and alerts you:

```bash
set -uo pipefail   # note: no -e
rc=0
for league in nba wnba; do
  if ! generate --league "$league" ...; then
    echo "::error::${league} failed"
    rc=1            # remember, but don't abort the other league
  fi
done
exit "$rc"          # still red if anything failed — after everyone ran
```

**Let downstream independent steps run despite an upstream failure** with
`if: ${{ !cancelled() }}`. The Bee step shares nothing with the crossword (no
games, no LLM), and the commit step should ship whatever *did* land:

```yaml
- name: Generate Bees
  if: ${{ !cancelled() }}   # a crossword outage must not drop the Bees
- name: Commit and push
  if: ${{ !cancelled() }}   # ship partial success; the failed step is already red
```

**Distinguish "no work" from "failure."** A no-games day must be exit 0 (the
CLI already does this via a `NoGamesSignal`), so it never trips the isolation
machinery — only genuine errors do.

## Why This Matters

`set -e` + a loop is the default way to write a multi-item batch script, and
it's exactly wrong when the items are independent: it converts any single
transient failure into a total outage of the whole batch. The blast radius is
invisible until the day NBA's API flakes and you discover the WNBA puzzle and
both Bees silently never shipped.

The alternative shape (a matrix job with `fail-fast: false`) gives even
cleaner per-item isolation and logs, at the cost of multiple jobs racing to
push to the same branch (needs a rebase-before-push). For a small fixed set,
in-place isolation in one job is the smaller, lower-risk change.

## When to Apply

- Any scheduled job that produces multiple independent artifacts in one run.
- The moment a batch loop runs under `set -e` and the items don't depend on
  each other — that's the bug waiting to happen.

## When NOT to apply

If the steps are genuinely dependent (step B is meaningless if step A failed),
`set -e` fail-fast is correct — you *want* to stop. Isolation is for
*independent* work.

## Related

- Commit: `91a1a0d` (per-league isolation + !cancelled() + honest commit message)
- [Publish vs slate date](2026-06-01-publish-vs-slate-date.md) — why the leagues are independent in the first place
