---
title: A scoreboard cache that never invalidates will mask real games — gate reuse on "fresh AND final"
date: 2026-06-09
category: solutions
module: pipeline/nba_mini/ingest/nba_stats
problem_type: bug_pattern
component: pipeline
severity: high
applies_when:
  - "Caching a time-evolving external response (scoreboard, standings, live feed) keyed only by date/id"
  - "A schema/endpoint migration only runs on the live-fetch path, not on cached payloads"
  - "A scheduled job fetches data that may not be settled yet at fetch time"
symptoms:
  - "Site shows an old puzzle; the league with a late game is the one missing"
  - "Re-running by hand 'fixes' it intermittently (because a re-fetch finally lands a final slate)"
  - "Parser crashes with 'line score for game ... team None not found' even after a V2->V3 migration"
root_cause: stale_cache
resolution_type: code_fix
tags: [caching, cache-invalidation, ingestion, scoreboard, nba, schema-migration, scheduling]
---

# Stale scoreboard cache masks real games

## Problem

The NBA daily crossword went silently missing for **five days** (2026-06-05
through 06-09, the NBA Finals) while WNBA generated fine every day. Re-running
the NBA generator by hand crashed with the *same* error a prior migration was
supposed to have killed:

```
ERROR nba.com ingest failed for 2026-06-09:
      line score for game 0042500402 team None not found in response
```

That game id (`...402`, Finals Game 2) had nothing to do with the date being
generated (the slate was Game 3, `...403`). The mismatch was the tell.

## Root cause — TWO stale-cache hazards, compounding

The ingest caches each day's scoreboard to
`~/.cache/nba-mini/nba_stats/scoreboard-<league>-<date>.json` and **never
invalidated it**. Two independent poisoned entries stacked up:

1. **Pre-tip-off snapshot cached as a 0-0 stub.** The 06-08 cache was written by
   the morning run *before* Game 3 tipped (8:30pm ET). It recorded the game as
   scheduled (`GAME_STATUS_TEXT = "8:30 pm ET"`, score 0-0, period 0). Every
   later run read that stub from disk, the box-score "was it played" gate
   dropped it as not-yet-tipped, and the walk-back skipped right past the real
   game — **forever**, because nothing ever refreshed the cache entry.

2. **Pre-V3 raw blob read past the adapter.** The walk-back then kept going back
   until it hit a months-old `scoreboard-nba-2026-06-05.json` written in the
   **raw ScoreboardV2 shape** (null `HOME_TEAM_ID`, one missing line-score row —
   the exact broken-V2 data the [[2026-06-03-nba-scoreboard-pts-unreliable]]
   V3 migration exists to avoid). The V3 adapter only runs on **live** fetches;
   a cached raw-V2 payload is read straight off disk and fed to the parser,
   which crashed and aborted the entire walk-back.

The migration didn't help because **the bad data never came from the API — it
came from disk.** A fix that lives on the live-fetch path is invisible to cached
payloads.

WNBA was unaffected only by luck: its caches for the relevant days happened to
be written *after* those games finished.

## Solution

Gate cache **reuse** on two conditions, and gate cache **writes** on one
(`pipeline/nba_mini/ingest/nba_stats.py`):

- **Reuse only if `_scoreboard_cache_is_fresh`** = the GameHeader column
  signature matches the current adapted shape (`_ADAPTED_GAME_HEADER_COLUMNS`)
  **AND** every game is Final (`_scoreboard_is_final`). Wrong shape ⇒ pre-V3
  blob ⇒ re-fetch. Not final ⇒ pre-tip-off/in-progress snapshot ⇒ re-fetch.
- **Persist only a final slate.** A non-final snapshot is never written, so a
  0-0 stub can't mask a real result on a later run. An **empty** slate counts as
  settled (a genuine no-games day) and is cached, so off-days don't re-fetch.
- **On any structural surprise, re-fetch rather than raise.** A stale *cache*
  must never be the thing that aborts ingest — degrade to a live call.

The adapter's emitted column tuples were extracted to module constants
(`_ADAPTED_GAME_HEADER_COLUMNS` / `_ADAPTED_LINE_SCORE_COLUMNS`) so the writer
and the freshness check share one definition of "current shape."

Immediate cleanup: deleted the 24 stale raw-V2 scoreboard caches on disk (they
re-fetch on demand now, but leaving them is just cruft).

## What to check first next time

- **Which tenant/league is missing?** If one feed works and a parallel one
  doesn't, the difference is almost always *data* (cache/state), not shared code
  or auth. (Same triage heuristic as the SSO incident — see Don't-Conflate in
  [[2026-06-04-sso-token-no-refresh-unattended-jobs]].)
- **Does the failing id match the date being generated?** An id from a different
  day in the error == you're parsing a cached payload from another day (the
  walk-back reached back to a poisoned entry).
- **Was the cache written before the event settled?** `ls -la` the cache dir;
  compare the file mtime to the game's tip-off time.

## Prevention

- **Never cache a time-evolving resource without an invalidation condition.**
  "Cache the scoreboard" is only safe once the scoreboard is *final*. Caching a
  snapshot of something still in motion guarantees a stale read later.
- **A schema migration on the live path doesn't migrate data at rest.** When you
  change a payload shape, either (a) version/namespace the cache so old blobs
  miss, or (b) validate the cached shape on read and re-fetch on mismatch. This
  fix does (b).
- **A stale cache should degrade, not crash.** Reading bad cache data must fall
  back to a live fetch, never raise an error that aborts the run.

## Related Issues

- [[2026-06-03-nba-scoreboard-pts-unreliable]] — the V2→V3 migration this bug
  sailed around by living in the cache
- [[2026-06-01-per-league-cache-namespace]] — the same cache, an earlier
  cache-key hazard
- [[2026-06-04-sso-token-no-refresh-unattended-jobs]] — the "one symptom, two
  causes; triage each to its own root" lesson, reused here
