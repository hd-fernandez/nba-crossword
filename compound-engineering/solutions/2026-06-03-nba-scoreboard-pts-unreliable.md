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
root_cause: wrong_api
resolution_type: code_fix
tags: [nba-api, scoreboard, boxscore, data-source, date-gating, ingest]
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

## Related Issues

- [[2026-06-01-provisional-state-self-correction]] — another ingest "absence vs zero" trap
- [[2026-06-03-verify-before-you-claim]] — the "119 posts" half of the same investigation
