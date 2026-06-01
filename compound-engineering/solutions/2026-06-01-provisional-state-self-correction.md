---
title: Self-correct provisional client state instead of guessing at the ambiguous moment
date: 2026-06-01
category: solutions
module: web/lib/storage + web/components/PuzzlePage
problem_type: design_pattern
component: frontend
severity: medium
applies_when:
  - "A client records a sticky decision from an observation that is genuinely ambiguous at the time"
  - "A later, more informative observation can confirm or refute that earlier decision"
tags: [ux, state-management, streaks, idempotency, localstorage]
---

# Self-correct provisional state instead of guessing once

## Context

The streak feature treats an "off-day" (a day with no puzzle) as a non-breaking
skip — your streak survives a league's off-day. The page marked today as an
off-day whenever today's puzzle was absent and it served a fallback instead.

The ambiguity: at load time, "today's file 404s" has two indistinguishable
causes — a *genuine* off-day (the league didn't play and never will for that
date), or *cron lag* (the puzzle exists, the generator just hasn't run yet).
The original code marked the day off in both cases and wrote it permanently to
`knownOffDays`. On a real game day hit during cron lag, that permanently
granted the user a free streak skip they didn't earn.

## Guidance

Don't try to resolve the ambiguity at the ambiguous instant — you can't. Mark
provisionally, then **self-correct when a later observation disambiguates.**

When today's puzzle later resolves as genuinely present (`isToday === true`),
clear any off-day that an earlier lagged load recorded for today:

```ts
if (!resolved.isToday) {
  markOffDay(league, today);          // provisional: today's file is absent
} else {
  clearOffDayIfMarked(league, today); // correction: real puzzle showed up
}
```

Make the clear cheap and unconditional: `clearOffDay` returns the same state
reference when the date wasn't marked, and `clearOffDayIfMarked` skips the
persist entirely in that case, so calling it on every present-today load costs
nothing.

## Why This Matters

The instinct is to make the marking moment smarter — but no amount of cleverness
distinguishes "off-day" from "not generated yet" from a single 404. The
information that resolves it simply doesn't exist yet at that moment; it arrives
later when the file appears. Designing for *eventual* correction is more honest
and far simpler than a heuristic that's wrong some fraction of the time and
leaves permanent residue when it is.

General shape: **provisional write on ambiguous signal → idempotent correction
on the disambiguating signal.** The correction must be a no-op in the common
case so it's free to call eagerly.

## When to Apply

- Any sticky client decision derived from a signal that a later event can
  confirm/refute (optimistic UI, offline queues, "seen" markers, streak/skip
  logic).
- Whenever you're tempted to add branching to make a single ambiguous read
  "smarter" — ask instead whether a later read can just fix it.

## Related

- Commit: `91a1a0d` (clearOffDay self-correction)
- [Index + walk-back fallback](2026-06-01-index-walk-back-fallback.md) — where the `isToday` signal that drives this is computed
