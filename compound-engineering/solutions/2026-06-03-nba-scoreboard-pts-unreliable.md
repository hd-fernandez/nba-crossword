---
title: NBA scoreboard PTS is unreliable — the boxscore TeamStats table is the source of truth
date: 2026-06-03
category: solutions
module: pipeline/nba_mini/ingest/nba_stats
problem_type: integration_issue
component: integration
severity: high
symptoms:
  - "Scoreboard endpoint returns PTS=None even for games that finished hours ago"
  - "Scoreboard lists future/scheduled games alongside completed ones"
  - "Pipeline fabricated 0-0 'finals' for games that had real scores"
  - "ScoreboardV2 returns a None home-team id + a missing opponent row for a playoff game, crashing the parser"
root_cause: wrong_api
resolution_type: code_fix
tags: [nba-api, scoreboard, scoreboardv3, boxscore, data-source, date-gating, ingest, playoffs]
updated: 2026-06-04
---

# NBA scoreboard PTS is unreliable; trust the boxscore

## Problem

The daily pipeline pulled game results from the `nba_api` scoreboard endpoint
and treated its `PTS` field as the score. That field is `None` even for
long-finished games, so the pipeline shipped fabricated **0-0** results that the
clue-writer then built fake narratives around.

## Symptoms

- Scoreboard `PTS` (and `TEAM_*_PTS`) is `None` for games that ended hours ago.
- The scoreboard also lists **future** scheduled games with no scores.
- Downstream: 0-0 "results" and hallucinated game recaps.

## What Didn't Work

- Treating scoreboard `PTS` as authoritative and coercing `None → 0`. That is
  exactly what manufactured the 0-0 finals.

## Solution

Two changes, both in `ingest/nba_stats.py`:

1. **Gate on date, not on the scoreboard's notion of "done."** Keep only games
   whose `GAME_DATE_EST[:10]` is strictly **before** today (the publish date).
   A past game is a real result; today/future games are not.

   ```python
   def _parse_scoreboard(payload, *, today):
       games = []
       for row in rows:
           gdate = _parse_game_date(row["GAME_DATE_EST"])
           if gdate >= today:        # drop scheduled / in-progress
               continue
           games.append(...)         # leave PTS as-is; do NOT coerce to 0
       return games
   ```

2. **Recover the real score from the boxscore `TeamStats` table** — that is the
   source of truth, not the scoreboard. Confirm the game was actually played by
   checking that `PlayerStats` logged minutes, then read team points from
   `TeamStats`:

   ```python
   def _team_scores_from_boxscore(payload) -> dict[str, int]:
       # {tri_code: PTS} read from the TeamStats table
       ...
   def _boxscore_was_played(player_rows) -> bool:
       return any(_minutes(r) for r in player_rows)
   ```

If a day's slate yields no played games, emit a `NoGamesSignal` rather than an
empty digest, so downstream can say "no games" instead of inventing one.

## Why This Works

The scoreboard is a schedule/status feed; its score fields are flaky and
populated inconsistently. The boxscore `TeamStats` row is the settled, official
team total. Date-gating removes scheduled games the scoreboard mixes in;
boxscore-minutes confirm the game happened; `TeamStats` supplies the true score.

## Prevention

- **Never trust scoreboard `PTS`. Read scores from boxscore `TeamStats`.**
- Gate "prior games" on `game_date < today` — don't rely on a status flag.
- Don't coerce a missing score to `0`; absence ≠ zero. A missing score means
  "don't use this game," not "0-0."
- For playoff grounding, `BoxScoreSummaryV3` `seriesText`/`seriesGameNumber`
  give series state (V2 has known gaps after 4/10/2025).

## Update 2026-06-04 — V2 doesn't just have flaky PTS; it serves broken data. Switch to V3.

The next morning (NBA Finals **Game 1**, game id `0042500401`) the daily run
crashed outright: `line score for game 0042500401 team None not found in
response`. ScoreboardV2 had returned, for that one playoff game, a **`None`
`HOME_TEAM_ID`** and **only one team's LineScore row** (NYK, with `PTS=None`),
status still showing the tip time. The home team (San Antonio) simply wasn't in
the payload, so the team-id lookup found nothing and raised.

This is unfixable inside V2 — the data to recover the home team *isn't in the
response*. And `nba_api` itself now emits a deprecation warning on V2: *"known
issues with line score data … Please use ScoreboardV3 instead. ScoreboardV3 is
fully backward compatible."* V3 returned the same game perfectly: both teams,
tri-codes, ids, and final scores (`SAS 95, NYK 105`, status `Final`) in one
clean call.

**Fix:** fetch **ScoreboardV3** and adapt its `scoreboard.games[]` list into the
V2 `resultSets` shape (`GameHeader` + `LineScore`) the parser already consumes,
at the client boundary (`_v3_scoreboard_to_resultsets`). The well-tested parser
and its whole suite stay unchanged; the V2 `resultSets` shape is now a purely
**internal intermediate format**, not a live source.

- **Map `gameEt` → `GAME_DATE_EST`** (V3 dates are ISO-with-zone; the parser
  reads the leading 10 chars). Prefer `gameEt` over `gameTimeUTC` so a late ET
  evening game doesn't roll to the next UTC day and trip the future-game gate.
- **Pass-through guard:** if the payload isn't V3-shaped (`no scoreboard.games`),
  return it untouched — so V2-shaped test fixtures and already-adapted cached
  payloads flow through unchanged, and an unrecognized shape still fails *loud*
  downstream (`missing 'resultSets'`) rather than silently.
- **Skip-and-log a malformed game** (missing id / either team's id or tri-code)
  instead of letting a `None` tri-code reach `GameSummary` validation — one bad
  game would otherwise abort the **entire** slate (the very all-or-nothing
  failure the switch was removing). A genuinely empty slate still →
  `NoGamesSignal`.

The boxscore-`TeamStats`-is-source-of-truth rule above **still holds** — V3 fixed
the *crash* (missing team data), not necessarily score-field reliability. Keep
reading final scores from the boxscore.

### Added prevention
- **Prefer ScoreboardV3.** V2 is deprecated and serves broken line-score data
  for some games (playoffs especially). When `nba_api` prints a deprecation
  pointer to a "fully backward compatible" successor, take it.
- **Adapt new API → tested internal shape at the boundary** when the parser is
  well-covered: smallest blast radius, suite stays green, no parser rewrite.
- **A per-item ingest fault must not sink the batch.** Skip-and-log the bad
  record; never let one malformed game `None`-poison the whole slate.
- **Smoke-test against the real endpoint for the date that broke** (here, the
  Finals game) — not just hand-built fixtures. (See [[2026-06-03-verify-before-you-claim]].)

## Related Issues

- [[2026-06-01-provisional-state-self-correction]] — another ingest "absence vs zero" trap
- [[2026-06-03-verify-before-you-claim]] — the "119 posts" half of the same investigation
- [[2026-06-04-sso-token-no-refresh-unattended-jobs]] — the auth half of the same Finals-morning incident (why the local cron also didn't self-heal)
