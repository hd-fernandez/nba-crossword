# nba-crossword

A daily basketball-themed 5×5 mini crossword. Clues refresh every morning from yesterday's discourse — last night's games, the relevant subreddit, news, drama. Voice mix is wry-NYT, online-discoursey, and factual.

**Status:** v0 implemented on `feat/v0-foundation`. UX iteration round 1 shipped (photo bg, splash overlay, dismissable finish, auto-advance). Awaiting Snowflake Cortex auth to wire up real clue generation.

See:
- [compound-engineering/plans/](compound-engineering/plans/) — active implementation plan
- [compound-engineering/brainstorms/](compound-engineering/brainstorms/) — design docs for v0 (NBA crossword), v2 (multi-league WNBA), and v3 (Hoops Spelling Bee)

## Layout

- [pipeline/](pipeline/) — Python package that generates the daily puzzle. Runs on GitHub Actions.
- [web/](web/) — Next.js 16 PWA that serves the daily puzzle.
- [puzzles/](puzzles/) — daily JSON files committed by the pipeline (`YYYY-MM-DD.json`). At v2 this becomes `puzzles/<league>/<date>.json`.
- [compound-engineering/](compound-engineering/) — plans, brainstorms, reviews, learnings.

The pipeline and the web app communicate only through the daily JSON file. No runtime API contract; no shared state.

## Roadmap at a glance

- **v0** — NBA daily crossword, automated end-to-end. ✅ implemented; demo working locally.
- **v0.5** — N candidates per night + LLM-as-judge ranking + rate-and-rank loop for clue quality.
- **v1** — Native iOS / push / accounts / cloud-synced streaks / friend leaderboards.
- **v2** — WNBA as a first-class peer league (`/nba/`, `/wnba/`, smart default). Per-league streaks, contexts, palettes. See [multi-league brainstorm](compound-engineering/brainstorms/2026-05-21-multi-league-wnba-design.md).
- **v3** — Hoops Spelling Bee (NYT Bee mechanic, hoops names corpus, Rookie → GOAT tiers). See [Spelling Bee brainstorm](compound-engineering/brainstorms/2026-05-21-spelling-bee-design.md).
