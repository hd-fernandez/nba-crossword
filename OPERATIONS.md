# nba-crossword Operations

Operational runbook for the daily puzzle pipeline. This doc covers the cases when you need to touch it.

## ⚠️ Current status (2026-06-03): generation runs LOCALLY, not in CI

The GitHub Actions cron (`.github/workflows/daily-puzzle.yml`) is **currently down**. It was switched to generate clues with Claude on **Amazon Bedrock via GitHub OIDC** (commit `c2f6cfd`), but the AWS-side IAM setup was never completed — so the runner can't authenticate and the scheduled run fails every morning with `Could not load credentials from any providers`. Its red-run email is a **known, expected signal**, not a new problem.

**The active path is a local launchd job on Henry's Mac** (`scripts/`), which does the same generation using local AWS SSO Bedrock access, commits the puzzle JSON, and pushes to `main`:

- `scripts/daily-puzzle-local.sh` — generate both leagues' crosswords + Bees, commit, push.
- `scripts/com.nba-crossword.daily-puzzle.plist` — launchd agent, runs daily at **9:30 local**. Installed in `~/Library/LaunchAgents/`. Log: `/tmp/nba-crossword-daily.log`.
- Full setup + caveats: `scripts/README.md`.

Caveat: the laptop must be awake at 9:30 (launchd runs the job on next wake if asleep; missed runs don't stack). If the Mac is off for days the SSO refresh chain lapses — run `aws sso login --profile nba-bedrock` once to re-prime.

**To restore the hands-off CI cron:** an IAM admin on AWS account `042122908126` runs the setup in `compound-engineering/reference/bedrock-oidc-admin-handoff.md`, then `gh variable set AWS_BEDROCK_ROLE_ARN ...`. Currently parked (local job is good enough). The workflow now has a preflight step that fails with a clear message if that variable is still unset.

## Schedule

- **Active (local launchd):** daily at **9:30 local** (`StartCalendarInterval` in the plist). Adjust `Hour`/`Minute` there, then reinstall + reload.
- **CI cron (currently failing):** `0 10 * * *` — 10:00 UTC = 06:00 ET summer / 05:00 ET winter. DST drift is acceptable for v0.

## LLM authentication (no Anthropic API key anymore)

Clue generation runs **Claude on Amazon Bedrock**, not the direct Anthropic API. There is **no `ANTHROPIC_API_KEY` secret** — that was retired in `c2f6cfd`.

- **Locally:** uses the `nba-bedrock` AWS SSO profile (account `042122908126`, `us-east-1`). The local script sets `AWS_PROFILE=nba-bedrock` and `NBA_MINI_LLM_BACKEND=bedrock`. AWS CLI v2 refreshes the SSO token non-interactively, so no browser is needed day-to-day.
- **In CI (when restored):** the runner assumes an IAM role via GitHub OIDC — no long-lived secret. The role ARN lives in repo variable `AWS_BEDROCK_ROLE_ARN`.

## Generating / backfilling a day (run it yourself)

**Active method — local script** (since the CI cron is down). From the repo root:

```sh
scripts/daily-puzzle-local.sh                      # today (yesterday's slate)
scripts/daily-puzzle-local.sh 2026-05-12           # a specific date
scripts/daily-puzzle-local.sh 2026-05-12 --force   # overwrite an existing puzzle
```

It generates both leagues' crosswords + Bees, then commits and pushes whatever landed. A no-games day exits clean with nothing committed (the gap is correct — no backfill needed). Review the clues before/after if it's a live day; the critic gate is good but not perfect.

**Once the CI cron is restored,** the same thing runs via GitHub Actions:

```sh
gh workflow run "Daily Puzzle"
gh workflow run "Daily Puzzle" -f date=2026-05-12
gh workflow run "Daily Puzzle" -f date=2026-05-12 -f force=true
```

…or from the UI: **Actions → Daily Puzzle → Run workflow**, leaving inputs blank for yesterday's puzzle, or setting **date**/**force** to backfill or overwrite.

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

3. Trigger a fresh generation to overwrite:

   ```sh
   scripts/daily-puzzle-local.sh YYYY-MM-DD --force
   # or, when CI is restored:
   gh workflow run "Daily Puzzle" -f date=YYYY-MM-DD -f force=true
   ```

The site redeploys automatically: any push to `main` triggers `.github/workflows/deploy-pages.yml`, which rebuilds the static Next.js export and publishes to **GitHub Pages** (`https://hd-fernandez.github.io/nba-crossword/`) within a couple of minutes. (A `vercel.json` is also present for an alternative root-domain Vercel deploy.)

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

## Verifying the local job

Confirm the launchd agent is healthy:

```sh
launchctl list | grep nba-crossword              # is it loaded?
launchctl start com.nba-crossword.daily-puzzle   # run once now
tail -f /tmp/nba-crossword-daily.log             # watch it
```

A healthy run logs `AWS auth OK (...)`, then either commits/pushes new puzzle JSON or reports "No puzzle changes" (a no-games day or an already-generated date). After a real push, confirm the GitHub Pages deploy went green (Actions → Deploy to GitHub Pages) and the live site shows the new puzzle.

## Where things live

- **Local generator (active):** `scripts/daily-puzzle-local.sh`, `scripts/com.nba-crossword.daily-puzzle.plist`, `scripts/README.md`
- **CI workflow (currently failing):** `.github/workflows/daily-puzzle.yml`
- **Deploy workflow:** `.github/workflows/deploy-pages.yml` (static Next.js export → GitHub Pages)
- **Pipeline package:** `pipeline/nba_mini/` (entry point: `python -m nba_mini.generate`)
- **Web app:** `web/` (Next.js, static export)
- **Season context:** `pipeline/nba_mini/season_context.md`
- **Daily puzzles:** `puzzles/<league>/YYYY-MM-DD.json` (and `puzzles/<league>/bee/YYYY-MM-DD.json`)
- **Bedrock OIDC handoff:** `compound-engineering/reference/bedrock-oidc-admin-handoff.md`
- **Plan / design / learnings:** `compound-engineering/plans/`, `.../brainstorms/`, `.../solutions/`
