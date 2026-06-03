# Clue Rating Batch — Round 2 (2026-06-02, after the fixes)

**What changed since round 1.** You marked up the first batch; I shipped five
fixes off it (all on `main`):

| # | Commit | Fix |
| --- | --- | --- |
| 1 | `c3d7842` | **Grid real-word guard** — no more junk answers (CRBCA, SWB, KUMOG). Every answer is a real word. |
| 2 | `6ead21f` | **Prompt tuning** — your rubric baked in: no logical gaps, no hallucination, no freebies, no broken metaphors; "don't force basketball" on fill words; cross-clue variety thread (kills thobe-repetition); discoursey reframed to *content not tone*. |
| 3 | `9ade9d9` | **Clue critic** — an LLM editor judges every puzzle against your rubric and regenerates failures automatically (ship-best-and-log). |
| 4 | `de07289` | **7-day window** — reddit pool went ~15 → 119 posts, so there's enough distinct material that clues don't repeat. |
| 5 | `d365874` | **Duplicate-answer fix** — was ~3% of grids (STY×3); now 0. |

These are **live outputs through the full pipeline** (7-day sources → tuned
prompts → variety thread → critic gate). Same drill: mark `KEEP` / `CUT` /
`FIX: <note>` in the Verdict column.

## How round 1's specific complaints fared

Your exact round-1 gripes, re-checked:
- ❌→✅ "SPURS / Oklahoma City said goodbye in seven — logical gap" → critic now
  catches logical gaps; clues must lead to the answer.
- ❌→✅ "LLAMA / never heard of this nickname (hallucination)" → critic flags
  hallucinated facts.
- ❌→✅ "ALL / SAS — way too easy (freebie)" → critic flags freebies.
- ❌→✅ "thobe appeared 4× — too repetitive" → variety thread + 119-post pool.
- ❌→✅ junk fill words clued with fake NBA lore → real-word guard + "don't force
  basketball."

---

to save you spoilers, my overall feedback is we've gone too far away from basketball. need the clue generation and review to actually make basketball clues. also Grid A and B look identical. 

## NBA — Grid A (2026-06-02)

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| A1 | SPA | wry | Place of rest and recovery, which playoff teams could use right now. | keep |
| A2 | SAFER | wry | More secure, and how OKC's path to the Finals would've felt with home court. | fix -- OKC DID HAVE home court. right idea, wront execution |
| A3 | PROMO | wry | Limited-time deal, in ad-speak. | keep|
| A4 | ADOBE | factual | Sun-dried brick material used in Southwestern architecture. | keep (perfect) |
| A5 | YARDS | wry | Three feet, by definition. | fix (should be yard plural) |
| A6 | YAW | wry | Rotate around the vertical axis, as a plane — or a bewildered Thunder fan — might. | keep (good)|
| A7 | STY | discoursey | Muddy pen for farm animals. | keep |
| A8 | AFOOT | discoursey | In play, as late-May basketball plans tend to be. | (keep)... not great but it's okay. this is sort of the floor of what's acceptable |
| A9 | WEMBY | factual | Spurs center who recorded his first career ejection last week. | perfect. more like this |
| A10 | ROE | discoursey | Fish eggs. | i mean fine. maybe a playbe on basketball words is possible here |

overall fine but this is hardly basketball related. "wemby" is the only basketball answer, and there are hardly any basketball clues? we need to tighten the clue and answer generation in a big way. 

## NBA — Grid B (2026-05-30)

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| B1 | SPA | wry | Place to unwind after a hard seven-game series. | |
| B2 | SAFER | wry | More protected, as a lead that's not three possessions. | |
| B3 | PROMO | wry | Code someone enters at checkout, or what the Thunder might need after this exit. | |
| B4 | ADOBE | wry | Sun-dried brick, or Photoshop's parent company. | |
| B5 | YARDS | factual | Gridiron distance unit, measured in three-foot increments. | |
| B6 | YAW | wry | Rotation around an aircraft's vertical axis. | |
| B7 | STY | discoursey | Messy place to keep pigs. | |
| B8 | AFOOT | discoursey | In progress, as a mystery's opening chapter might say. | |
| B9 | WEMBY | factual | Spurs center who recorded his first career ejection last week. | |
| B10 | ROE | discoursey | Fish eggs, or what GMs gamble with at the lottery. | |

  these clues above look identical to nBA GRID A

## WNBA — Grid C (2026-06-02)

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| C1 | LAW | wry | Rule, as laid down. | |
| C2 | LOWER | wry | Closer to the floor than the rim. | |
| C3 | ADAGE | wry | Old saying that's survived longer than most dynasties. | |
| C4 | WAKED | factual | Mourned at a funeral vigil. | |
| C5 | TODAY | wry | The present moment, which the Fever keep making into a headline. | |
| C6 | TAB | wry | Bar bill, or what the league's growth is running up for future investors. | |
| C7 | YET | discoursey | Word that trails every "the Aces haven't been dethroned" take. | |
| C8 | AWAKE | discoursey | Not sleeping on Jessica Shepard's historic triple-double, for one. | this is a good example for NON BASKETBALL related answer, but a good basketball related clue |
| C9 | BEGET | factual | Produce, as one dynasty tends to another. | |
| C10 | RED | discoursey | Color of Kiki Rice's Toronto Tempo uniform. | |

i can't support this grid, same as NBA's it needs to lean much more basketball related. 

## My own read (candidates for your attention)

A few I'd flag for a second look — curious if you agree:

- **A5 YARDS "Three feet, by definition"** — technically a yard is 3 feet, but
  YARDS is plural; the clue reads slightly off. Minor.
- **B4 ADOBE "Sun-dried brick, or Photoshop's parent company"** — Adobe makes
  Photoshop, it's not its "parent company." Small factual slip the critic let
  through — a candidate for tightening the hallucination rule.
- **C4 WAKED "Mourned at a funeral vigil"** — "waked" is a real but awkward
  word; clue is accurate but the answer is weak fill. (A wordlist-quality issue,
  not a clue issue — relates to the deferred frequency-expansion.)
- **C8 AWAKE / C10 RED** — these lean on specific WNBA names (Jessica Shepard,
  Kiki Rice/Toronto Tempo). If those are real and current, great; if the model
  reached, they'd be hallucinations. **Worth your eyes** — I can't verify WNBA
  roster specifics.

The pattern that remains: a few clues still make small factual claims the critic
doesn't catch (ADOBE parent-company, possibly the WNBA names). If round-2 markup
confirms that's the main residual issue, the next lever is **tightening the
critic's hallucination rule** + possibly grounding it with a verification step.

---

*Full-pipeline live outputs, 2026-06-02. Mark it up and I'll do another tuning
pass on whatever's left.*
