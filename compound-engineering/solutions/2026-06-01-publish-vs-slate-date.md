---
title: Separate publish date from slate date; look back to each league's most recent games
date: 2026-06-01
category: solutions
module: pipeline/nba_mini/generate + ingest/nba_stats
problem_type: architecture_pattern
component: pipeline
severity: high
applies_when:
  - "A news/data-driven app publishes 'today's thing' but the underlying source data has gaps (off-days, holidays, weekends)"
  - "Different sub-feeds (leagues, regions, categories) have their own independent activity calendars"
tags: [dates, timezone, lookback, multi-league, data-pipeline]
---

# Publish date vs slate date, and per-league look-back

## Context

The original pipeline ingested **yesterday's** games and published a puzzle
for today. That breaks whenever a league didn't play yesterday: the user
reported the NBA Mini showing "May 29" on June 1, because the last NBA slate
before the generator ran was stale and nothing newer existed. WNBA and NBA
also have different calendars — on a given Monday the NBA's most recent slate
might be Saturday's while the WNBA played Sunday.

Conflating "the day we serve this puzzle" with "the day the games were played"
is the root design flaw. They are two different dates and need two fields.

## Guidance

**Split the date into two concepts** (see
[pipeline/nba_mini/schema.py](../../pipeline/nba_mini/schema.py)):

- `date` — the **publish date**: the day this puzzle is served as "today's."
  The frontend fetches by this date.
- `slate_date` — the day the underlying games were actually played. Usually
  `date - 1`, but can be older. Optional, for back-compat with puzzles authored
  before the field existed.

**Look back to the most recent slate per league, independently.**
`fetch_most_recent_games(start, *, league, max_lookback, ...)` walks back
day-by-day from `start` (inclusive) and returns the first day with games, or a
`NoGamesSignal` if the window (`MAX_LOOKBACK_DAYS = 10`) is exhausted. Each
league gets its own call, so an NBA off-day never blocks the WNBA puzzle and
vice versa.

**Seed off the publish date, not the slate.** Deterministic generation keys on
`date.toordinal()` so re-running for the same publish date is idempotent
regardless of which slate it resolved to.

**Use a DST-aware zone for the publish date.** `today_in_eastern` uses
`zoneinfo.ZoneInfo("America/New_York")`, matching the frontend's
`Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" })`. A fixed
UTC-offset approximation drifts by a day near local midnight in the non-DST
half of the year, so the pipeline could publish under a date the app isn't yet
asking for.

## Why This Matters

"Always look at yesterday" is the natural first cut and it's wrong the first
time the source skips a day — which, for any sports/events feed, is constant.
Modeling publish-vs-slate explicitly makes off-days a non-event: the puzzle
still publishes for today, it's just built from whenever the league last
played, and the UI can honestly say "from Saturday's games."

The per-league independence is the multi-tenant correctness point: a single
shared "yesterday" date couples feeds that have nothing to do with each other.

## When to Apply

- Any app that publishes a daily artifact derived from an external feed with
  gaps: sports, markets (weekends/holidays), event calendars.
- The moment you add a second independent feed (a second league, region, or
  category) — give each its own look-back rather than a shared date.

## When NOT to bother

If the source genuinely produces data every single day with no gaps, the split
is overhead. The trigger is "the source can skip a day."

## Related

- Commit: `82ad277` (WNBA generator + most-recent-slate logic), `91a1a0d` (DST publish date)
- [Per-league cache namespace](2026-06-01-per-league-cache-namespace.md)
- [Index + walk-back fallback](2026-06-01-index-walk-back-fallback.md) — the frontend's matching graceful-degradation half
