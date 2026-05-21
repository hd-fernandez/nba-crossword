---
title: "feat: Hoops Spelling Bee (v3 skeleton)"
type: feat
status: draft
date: 2026-05-21
origin: compound-engineering/brainstorms/2026-05-21-spelling-bee-design.md
---

# feat: Hoops Spelling Bee (v3 skeleton)

> **Status: draft skeleton.** Intentionally lighter than a full ce-plan. Promote when v2 (multi-league) is shipped and we're ready to start v3.

## Summary

NYT-style Spelling Bee where every valid answer is a hoops player / coach / owner / front-office last name. Three flavors: `/nba/bee`, `/wnba/bee`, `/bee` (combined). Hoops-flavored 9-tier ladder (Undrafted → GOAT). Pre-computed daily puzzles from a curated names corpus; no LLM in the loop, ~$0 operating cost.

## Requirements (from origin)

- R1. Hexagonal 7-letter board: 1 center, 6 outer; same mechanic as NYT Bee (min 4 letters, must use center, can repeat).
- R2. Names corpus per league (NBA, WNBA, combined). Length 4–10 last names; diacritics normalized; punctuation stripped for matching.
- R3. Daily puzzle picks center + outer letters such that 12–25 valid names exist with at least 1 pangram and a healthy difficulty spread.
- R4. Tier ladder: Undrafted, G League call-up, Rookie, Sophomore, Vet, All-Star, Champion, Hall of Famer, GOAT. Thresholds as % of max score.
- R5. Inline answer key on the daily Bee JSON (matches NYT pattern; minor spoiler concern accepted).
- R6. Per-Bee streak in localStorage; "Bee day" = at least Rookie tier.
- R7. Sequential per-flavor puzzle numbering: NBA Bee #N, WNBA Bee #N, Bee #N (combined) all count independently.
- R8. Share text: tier achieved + score + date + URL. Found-names list is *not* shared.

## Implementation units (rough)

- **U1.** Names corpus sourcing: pull active rosters from `nba_api` (both leagues) + historical scrape; build `pipeline/data/names_<league>.txt` with a documented "fame floor."
- **U2.** Bee schema (Python + TS): `BeePuzzle` model with center, outer, valid_names, pangrams, tier_thresholds, max_score.
- **U3.** Bee generator algorithm: pick (center + 6 outer) sets that hit the 12–25 valid names target with ≥1 pangram. Pre-compute a year of daily puzzles per flavor.
- **U4.** Tier calculation module: thresholds as % of max_score; map score → current tier + next-tier nudge.
- **U5.** Frontend hexagon component: 7 hex tiles, tap-or-type input, shuffle/delete/submit buttons. Mobile-first sizing.
- **U6.** Frontend tier display + score + found-names list (collapsed by default).
- **U7.** Frontend share component: tier-emoji + score + date + URL, no found-names leak.
- **U8.** localStorage shape extension: per-flavor Bee state + per-flavor streak.
- **U9.** Cross-promotional surfaces: link from crossword to today's Bee on the same league; link from Bee to crossword.
- **U10.** Refresh job (quarterly) to regenerate puzzles when corpus updates.
- **U11.** Tests for generator (12–25 names, ≥1 pangram, deterministic seed) and for tier math (boundary values).

## Risks (skeleton level)

- **Corpus quality.** "Fame floor" decisions have outsized UX impact. Too permissive → users see obscure 1980s journeyman names and feel cheated. Too restrictive → everyone hits GOAT in a week. Empirical tuning needed.
- **WNBA corpus depth.** Verify at plan time the corpus is large enough for satisfying daily Bees. Likely fine but unmeasured.
- **Pangram-required generator.** May be combinatorially expensive for some center letters; cap iterations and skip the day if no valid configuration found (fall back to a re-roll on the seed).
- **Diacritic handling consistency.** Display vs match must always agree. Bug surface.
- **Spoiler concern of inline answer key.** NYT does it; we accept the same trade. Document in a learnings file post-launch.
- **Mobile hex tap-target sizing.** NYT spent real time on this. Plan to reference their spacing.

## Open questions for full plan

All open questions live in the brainstorm under "Open questions parked for the implementation plan." Not duplicated here.

## Sources

- Origin brainstorm: [compound-engineering/brainstorms/2026-05-21-spelling-bee-design.md](../brainstorms/2026-05-21-spelling-bee-design.md)
- v0 plan (foundation): [2026-05-17-001-feat-nba-mini-v0-plan.md](2026-05-17-001-feat-nba-mini-v0-plan.md)
- Multi-league plan (predecessor): [2026-05-21-002-feat-multi-league-wnba-skeleton-plan.md](2026-05-21-002-feat-multi-league-wnba-skeleton-plan.md)
