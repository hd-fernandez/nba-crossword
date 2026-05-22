# nba-crossword Project Status

**Last updated:** 2026-05-22

This doc is the single-page answer to "where are we and what's left." Update it after every major milestone or session pause. Treat it as the always-current map; brainstorms and plans are the deeper docs underneath.

---

## What's done

- **v0 — NBA daily crossword.** Pipeline (Python on GH Actions), Next.js PWA frontend, schema, tests, deploy-ready. Working locally right now.
- **v2 — WNBA peer league.** Same URL, two leagues. `/nba` and `/wnba` with smart redirect at `/`. Per-league streaks, season contexts, palettes (NBA red / WNBA orange). Cross-league discovery chip.
- **UX iteration round 1.** Photo backdrop, splash overlay with sequential `#N`, dismissable finish modal, auto-advance on word completion, real fonts (Fraunces + Inter).

Branch: `feat/v0-foundation` on `hd-fernandez/nba-crossword`. Latest commit: `3c43847`.

---

## What's left, in order

### 1. LLM auth (blocked on you)

The pipeline currently calls a stub LLM. To generate real clues we need either a Snowflake service account or a personal Anthropic API key.

**Status:** asking the data team. Personal user can't `ALTER USER` to set keypair — needs admin help or a service-account provision.

### 2. Refine clues + answer picks

Once #1 clears: generate 3–5 real puzzles, Henry rates them, prompt files get edited based on the feedback, regenerate. This is the rate-and-rank loop. It's the work that makes the product *good*. Nothing about the engine changes — only the prompts in `pipeline/nba_mini/prompts/`.

### 3. Spelling Bee (v3)

Additive new game, doesn't need the LLM. Six implementation units — corpus, schema, generator algorithm, hexagon UI, tier ladder, share. **This is what we're building right now while #1 is blocked.**

### 4. Production deploy

Vercel hookup + GH Actions cron actually running on a schedule. Last step. Depends on #1 being resolved.

---

## Brainstorms + plans

- [v0 NBA crossword design](brainstorms/2026-05-15-nyt-nba-crossword-design.md)
- [v2 multi-league WNBA](brainstorms/2026-05-21-multi-league-wnba-design.md)
- [v3 Spelling Bee](brainstorms/2026-05-21-spelling-bee-design.md)
- [v0 plan](plans/2026-05-17-001-feat-nba-mini-v0-plan.md)
- [v2 skeleton plan](plans/2026-05-21-002-feat-multi-league-wnba-skeleton-plan.md)
- [v3 skeleton plan](plans/2026-05-21-003-feat-spelling-bee-skeleton-plan.md)

---

## Locked decisions

- **Domain:** `nbamini.app` stays. Brand recognition wins.
- **Default-league rules:** sticky last-played > calendar-driven (Oct–Apr NBA, May–Sep WNBA). NBA wins overlap-month tiebreak on cold start.
- **Per-league streaks** (independent, no merging).
- **Bee corpus:** last names + mononym first names + iconic nicknames. Fame floor: NBA 100 games OR award OR currently active; WNBA 3 seasons OR award OR currently active.
- **Bee tiers:** Undrafted → G League call-up → Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT.
- **Roadmap collapsed:** v0.5 quality work and v1 native-app work both deferred indefinitely. Going v0 → v2 → v3.

---

## Blockers

- **Snowflake auth.** Personal user can't set keypair. Asking data team for a service account or admin-installed keypair. Slack template lives in the May 22 conversation.

---

## Open trivia for later

- Real WNBA hero photo (currently a generic basketball shot).
- Production icons (192/512/180 raster).
- Vercel project setup (root dir = `web/`).
