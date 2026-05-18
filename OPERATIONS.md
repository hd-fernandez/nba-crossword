# nba-crossword Operations

Operational runbook for the daily puzzle pipeline. The pipeline runs automatically every morning via `.github/workflows/daily-puzzle.yml`. Most days you should not need to touch anything. This doc covers the cases when you do.

## Schedule

The cron is `0 10 * * *` (10:00 UTC every day):

- 06:00 ET in summer (EDT, UTC-4)
- 05:00 ET in winter (EST, UTC-5)

The DST drift is acceptable for v0. If feedback ever asks for a stable wall-clock time, switch to two cron entries gated on the month.

## Required secret

The pipeline needs one secret: `ANTHROPIC_API_KEY`.

Set it under **Settings → Secrets and variables → Actions → Repository secrets**. A run that fails on a missing key is the negative test that the secret is wired up correctly — fix it by adding the secret, then re-run via manual dispatch.

## Manually triggering the workflow

From the GitHub UI:

1. Go to **Actions → Daily Puzzle**.
2. Click **Run workflow** (top right).
3. Leave both inputs blank to generate yesterday's puzzle. Or:
   - **date**: an ISO date (`YYYY-MM-DD`) to backfill or regenerate that specific day's slate.
   - **force**: check this to overwrite an existing `puzzles/<date>.json`.
4. Click **Run workflow**.

You can also trigger from the CLI:

```sh
gh workflow run "Daily Puzzle"
gh workflow run "Daily Puzzle" -f date=2026-05-12
gh workflow run "Daily Puzzle" -f date=2026-05-12 -f force=true
```

## Backfilling a missed day

If the cron failed (or was skipped) and a day's puzzle is missing:

1. Manually dispatch the workflow with `date: YYYY-MM-DD` set to the missed slate's date. Leave `force` unchecked.
2. Watch the run. It will either:
   - Commit `puzzles/YYYY-MM-DD.json` and push to `main`, or
   - Exit cleanly with no commit if it was actually a no-games day (in which case the gap was correct and no backfill is needed).

## Rolling back a bad puzzle

If a published puzzle is unfair, broken, or otherwise bad:

1. Find the offending commit:

   ```sh
   git log --oneline -- puzzles/YYYY-MM-DD.json
   ```

2. Revert it:

   ```sh
   git revert <commit-sha>
   git push origin main
   ```

3. Trigger a fresh generation with `force: true` to overwrite:

   ```sh
   gh workflow run "Daily Puzzle" -f date=YYYY-MM-DD -f force=true
   ```

The Vercel deploy will pick up the new puzzle JSON within a few minutes (the service worker uses a network-first strategy for `/puzzles/*.json`).

## Updating season context

The clue-writing prompt prepends `pipeline/nba_mini/season_context.md`. Edit it whenever the calendar phase changes (regular season → play-in → playoff round transitions, post-Finals dormancy, draft, summer league, training camp, season tip-off).

The loader hashes the file's bytes and stamps the resulting hash into every generated puzzle's `season_context_version` field, so the very next pipeline run picks up your edits automatically. No code change, no redeploy.

Workflow:

```sh
$EDITOR pipeline/nba_mini/season_context.md
git add pipeline/nba_mini/season_context.md
git commit -m "chore(season): update context for <phase>"
git push
```

## Verifying after first push

Before fully trusting the cron, do one manual smoke run:

1. Dispatch the workflow with `date` set to a known good past game day (e.g. an obvious 8-game Tuesday in the regular season).
2. Confirm the run pushes a new `puzzles/<date>.json` to `main`.
3. Dispatch a second run with `date` set to a known no-games day (e.g. the off-day after a Finals series end). Confirm it exits clean with no commit.
4. The next morning, confirm the scheduled run produced the day's puzzle on its own.

## Where things live

- **Workflow:** `.github/workflows/daily-puzzle.yml`
- **Pipeline package:** `pipeline/nba_mini/` (entry point: `python -m nba_mini.generate`)
- **Season context:** `pipeline/nba_mini/season_context.md`
- **Daily puzzles:** `puzzles/YYYY-MM-DD.json`
- **Plan / design:** `context-engineering/plans/`, `context-engineering/brainstorms/`
