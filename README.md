# nba-crossword

A daily NBA-themed 5×5 mini crossword. Clues refresh every morning from yesterday's NBA discourse — last night's games, r/nba conversation, news, drama. Voice mix is wry-NYT, online-discoursey, and factual.

**Status:** v0 in progress. See [compound-engineering/plans/](compound-engineering/plans/) for the active implementation plan and [compound-engineering/brainstorms/](compound-engineering/brainstorms/) for the design doc.

## Layout

- [pipeline/](pipeline/) — Python package that generates the daily puzzle. Runs on GitHub Actions.
- [web/](web/) — Next.js 14 PWA that serves the daily puzzle.
- [puzzles/](puzzles/) — daily JSON files committed by the pipeline (`YYYY-MM-DD.json`).
- [compound-engineering/](compound-engineering/) — plans, brainstorms, reviews, learnings.

The pipeline and the web app communicate only through the daily JSON file. No runtime API contract; no shared state.
