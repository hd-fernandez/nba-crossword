---
title: Namespace external-fetch caches by tenant so same-date data from different feeds doesn't collide
date: 2026-06-01
category: solutions
module: pipeline/nba_mini/ingest/nba_stats
problem_type: bug_pattern
component: pipeline
severity: medium
applies_when:
  - "Caching responses from a parameterized external API keyed by a value (date) that repeats across tenants/leagues/regions"
  - "Adding a second tenant to code that originally assumed one"
tags: [caching, multi-tenant, cache-key, ingestion]
---

# Per-league cache namespace

## Context

The scoreboard ingest caches responses to disk to avoid hammering nba.com on
re-runs. The original single-league cache key was just the date:
`scoreboard-{iso}.json`. When WNBA support was added, both leagues fetch a
scoreboard for the *same* date — so without a change they'd read and write the
**same cache file**, and whichever league ran second would silently get the
first league's games.

## Guidance

Put the tenant in the cache key. The key became
`scoreboard-{league}-{iso}.json`, and a single client instance binds its
`league_id` (`"00"` for NBA, `"10"` for WNBA) up front so every fetch through
it is league-scoped:

```python
LEAGUE_IDS = {"nba": "00", "wnba": "10"}

class NbaApiStatsClient:
    def __init__(self, league: League = "nba"):
        self.league_id = LEAGUE_IDS[league]
    # cache key: f"scoreboard-{league}-{iso}.json"
```

The look-back loop reuses one client across all probed dates, so the bound
league + namespaced cache are shared correctly across the whole walk.

## Why This Matters

This is a textbook silent-correctness bug: nothing errors, the cache "works,"
and you get plausible-but-wrong data (NBA games under a WNBA puzzle). It only
surfaces if you happen to eyeball the output. The general rule: **when a cache
key is derived from a value that isn't unique across all the dimensions you now
vary, the key is wrong.** Adding a tenant dimension to single-tenant code is
the classic trigger — the date was a sufficient key for one league and a
collision for two.

## When to Apply

- Any time you add a second tenant/league/region/account to code that caches
  external responses by a key that repeats across that new dimension.
- Audit existing cache keys whenever you parameterize a previously-fixed input.

## When NOT to worry

If the cached value genuinely doesn't depend on the new dimension (e.g. a
global config fetch), a shared key is fine and namespacing is noise.

## Related

- Commit: `82ad277` (WNBA generator support)
- [Publish vs slate date](2026-06-01-publish-vs-slate-date.md) — the broader per-league independence this supports
