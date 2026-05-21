---
title: "feat: multi-league WNBA expansion (v2 skeleton)"
type: feat
status: draft
date: 2026-05-21
origin: compound-engineering/brainstorms/2026-05-21-multi-league-wnba-design.md
---

# feat: multi-league WNBA expansion (v2 skeleton)

> **Status: draft skeleton.** This is intentionally lighter than a full ce-plan. It names the implementation units and the risk surfaces so a future planning session has a head start. Promote to a full plan when v0/v0.5 are shipped and we know multi-league is the next priority.

## Summary

Add WNBA as a first-class peer to NBA. Same product, two leagues, smart-default routing at `/`, separate streaks, separate season contexts, separate visual identities. The frontend gains a league prefix in URLs and a league toggle in the header. The pipeline runs once per league per day.

## Requirements (from origin)

- R1. Schema gains a required `league: "nba" | "wnba"` field.
- R2. Storage layout becomes `puzzles/<league>/<date>.json`. Existing puzzles back-migrate to NBA.
- R3. Pipeline runs once per league per day; no-games-day rules apply per league.
- R4. Frontend default-league selection follows the rules in the brainstorm: sticky last-played, calendar-driven cold start, in-season tiebreak.
- R5. Per-league streaks. Existing user state migrates: old flat fields → `{ nba: {...}, wnba: {...} }`.
- R6. Per-league visual identity (color, photo, title text). NBA red, WNBA orange.
- R7. Cross-league discovery surface ("Also today: WNBA Mini #N") when both leagues have a fresh puzzle.

## Implementation units (rough)

- **U1.** Schema migration (Python + TS): add `league` field; back-fill existing puzzle JSON.
- **U2.** Pipeline league parameter: thread `league` through ingest (Reddit subreddit + nba_api endpoints), season context, generate.py CLI.
- **U3.** Per-league season context files (`season_context_nba.md`, `season_context_wnba.md`).
- **U4.** GH Actions cron: parallel jobs per league with shared install + secrets.
- **U5.** Frontend routing: restructure `app/` with `(league)/nba/` and `(league)/wnba/` route groups; `/` becomes a smart redirect.
- **U6.** Per-league localStorage shape; one-time migration on v2 launch.
- **U7.** League toggle in the header; cross-league discovery chip.
- **U8.** WNBA visual treatment: orange palette, separate hero photo, title swap.
- **U9.** WNBA wordlist overlay (only if needed empirically).
- **U10.** Tests for the routing rules (default-selection truth table) and for the per-league streak math.

## Risks (skeleton level)

- `nba_api` WNBA endpoint coverage may be thinner than expected. Mitigation: confirm at full-plan time; fallback is basketball-reference scrape.
- Pre-launch question: is `nbamini.app` the right brand for two leagues, or do we rebrand to something league-neutral? Punt to v2 plan time.
- Migration: existing puzzles need a one-shot script, and the frontend needs to handle both old (`puzzles/<date>.json`) and new (`puzzles/<league>/<date>.json`) paths during the transition. Or we write a single migration commit and break old URLs.
- WNBA Unsplash CC0 photo depth — verify there's enough imagery. Worst case, single hero shot per league for v2.

## Open questions for full plan

All open questions live in the brainstorm under "Open questions parked for the implementation plan." Not duplicated here.

## Sources

- Origin brainstorm: [compound-engineering/brainstorms/2026-05-21-multi-league-wnba-design.md](../brainstorms/2026-05-21-multi-league-wnba-design.md)
- v0 plan (foundation): [2026-05-17-001-feat-nba-mini-v0-plan.md](2026-05-17-001-feat-nba-mini-v0-plan.md)
