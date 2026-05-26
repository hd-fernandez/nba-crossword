# nba-crossword Project Status

**Last updated:** 2026-05-26

This doc is the single-page answer to "where are we and what's left." Update it after every major milestone or session pause. Treat it as the always-current map; brainstorms and plans are the deeper docs underneath.

---

## What's done

- **v0 — NBA daily crossword.** Pipeline (Python on GH Actions), Next.js PWA frontend, schema, tests, deploy-ready.
- **v2 — WNBA peer league.** `/nba` and `/wnba` with smart redirect at `/`. Per-league streaks, season contexts, palettes (NBA red / WNBA orange). Cross-league discovery chip.
- **v3 — Spelling Bee.** Hand-curated names corpus + active-roster auto-merge from `nba_api`. Six implementation units (corpus → schema → generator → hex UI → tier ladder → share). Three routes live: `/nba/bee`, `/wnba/bee`, `/all/bee`. GOAT celebration modal, share text, finish-dismiss state.
- **UX iteration round 1.** Photo backdrop, splash overlay with sequential `#N`, dismissable finish modal, auto-advance on word completion, real fonts (Fraunces + Inter).

Branch: `main` on `hd-fernandez/nba-crossword`. Latest commit: `cdba564`. Tests: 219 pipeline + 151 web passing. Routes: 7.

---

## What's left, in order

### 1. LLM auth (blocked on you)

The pipeline currently calls a stub LLM. To generate real clues we need either a Snowflake service account or a personal Anthropic API key.

**Status:** asking the data team. Personal user can't `ALTER USER` to set keypair — needs admin help or a service-account provision.

### 2. Refine clues + answer picks

Once #1 clears: generate 3–5 real puzzles, Henry rates them, prompt files get edited based on the feedback, regenerate. This is the rate-and-rank loop. It's the work that makes the product *good*. Nothing about the engine changes — only the prompts in `pipeline/nba_mini/prompts/`.

### 3. Production deploy

Vercel hookup + GH Actions cron actually running on a schedule. Last step. Depends on #1 being resolved.

### 4. (Optional) U7 — Bee generator algorithm tuning

WNBA Bees still cap at ~3–4 valid names per puzzle even after expanding the corpus to ~150 names. Diagnosed as algorithm bottleneck, not data depth: the greedy first-match board-pick walks away from richer boards. Broader board search + scoring would lift NBA from ~10 to 15+ and WNBA into the same range. See [solutions/2026-05-26-bee-v3.md](solutions/2026-05-26-bee-v3.md).

---

## Brainstorms + plans

- [v0 NBA crossword design](brainstorms/2026-05-15-nyt-nba-crossword-design.md)
- [v2 multi-league WNBA](brainstorms/2026-05-21-multi-league-wnba-design.md)
- [v3 Spelling Bee](brainstorms/2026-05-21-spelling-bee-design.md)
- [v0 plan](plans/2026-05-17-001-feat-nba-mini-v0-plan.md)
- [v2 skeleton plan](plans/2026-05-21-002-feat-multi-league-wnba-skeleton-plan.md)
- [v3 skeleton plan](plans/2026-05-21-003-feat-spelling-bee-skeleton-plan.md)
- [v3 learnings](solutions/2026-05-26-bee-v3.md)

---

## Locked decisions

- **Domain:** `nbamini.app` stays. Brand recognition wins.
- **Default-league rules:** sticky last-played > calendar-driven (Oct–Apr NBA, May–Sep WNBA). NBA wins overlap-month tiebreak on cold start.
- **Per-league streaks** (independent, no merging).
- **Bee corpus:** last names + mononym first names + iconic nicknames. Fame floor: NBA 100 games OR award OR currently active; WNBA 3 seasons OR award OR currently active.
- **Bee tiers:** Undrafted → G League call-up → Rookie → Sophomore → Vet → All-Star → Champion → Hall of Famer → GOAT.
- **Roadmap collapsed:** v0.5 quality work and v1 native-app work both deferred indefinitely. v0 → v2 → v3 shipped.

---

## Blockers

- **Snowflake auth.** Personal user can't set keypair. Asking data team for a service account or admin-installed keypair. Slack template lives in the May 22 conversation.

---

## Open trivia for later

- Real WNBA hero photo (currently a generic basketball shot).
- Production icons (192/512/180 raster).
- Vercel project setup (root dir = `web/`).
- Historical roster fold-in with fame-floor filter (NBA pre-active, WNBA pre-active).
