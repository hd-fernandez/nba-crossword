# scripts/

## Local daily-puzzle generator (laptop stopgap)

The GitHub Action (`.github/workflows/daily-puzzle.yml`) is blocked: it can't
authenticate to Bedrock until an AWS admin completes the OIDC/IAM setup
(`compound-engineering/reference/bedrock-oidc-admin-handoff.md`). Until then,
generate the daily puzzles locally — your machine's `nba-bedrock` SSO profile
already has Bedrock access, and AWS CLI v2 refreshes the SSO token
non-interactively (no browser) as long as the refresh-token chain is alive.

### Files

- `daily-puzzle-local.sh` — generates both leagues' crosswords + Bees, commits, pushes.
- `com.nba-crossword.daily-puzzle.plist` — launchd agent to run it daily at 9:30 local.

### Run by hand

```bash
scripts/daily-puzzle-local.sh                 # today
scripts/daily-puzzle-local.sh 2026-06-02 --force   # backfill / regenerate a date
```

### Schedule it (launchd)

```bash
cp scripts/com.nba-crossword.daily-puzzle.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.nba-crossword.daily-puzzle.plist
launchctl list | grep nba-crossword         # confirm loaded
launchctl start com.nba-crossword.daily-puzzle   # run once now to test
tail -f /tmp/nba-crossword-daily.log
```

Uninstall: `launchctl unload ~/Library/LaunchAgents/com.nba-crossword.daily-puzzle.plist && rm ~/Library/LaunchAgents/com.nba-crossword.daily-puzzle.plist`

### Caveats

- **Laptop must be awake at run time.** If asleep/off, launchd runs the job on
  next wake (missed runs don't stack). A no-games day is a clean no-op.
- **If SSO lapses** (machine off for days), the script exits with a clear message;
  run `aws sso login --profile nba-bedrock` once to re-prime, then it self-sustains.
- This is a **bridge**, not the destination. The real fix is the OIDC handoff so
  CI self-serves and the laptop isn't in the loop.
