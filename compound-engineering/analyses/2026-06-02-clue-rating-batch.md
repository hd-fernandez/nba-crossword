# Clue Rating Batch — 2026-06-02

**Purpose:** First real round of clue-quality feedback. These are *live* clues from the
wider-source pipeline (7 NBA subreddits + 3-day recency window, Bedrock/Sonnet), generated
2026-06-02. You mark each one, hand it back, and I tune the prompt files
(`pipeline/nba_mini/prompts/{candidate_answers,clue_factual,clue_wry,clue_discoursey}.md`),
regenerate, and we compare.

## How to mark

Edit the `Verdict` column inline. Use any of:

- **KEEP** — ship-quality as written
- **CUT** — bad clue; tells me the *voice/style* is wrong for this answer
- **FIX: <note>** — good answer, clue needs a specific change (write what you'd want)

Optional: tweak the `Voice` if you think a different register (factual / wry / discoursey)
would suit the answer better. Add free notes anywhere — I read the whole file.

## ⚠️ The big finding (read first)

Every grid splits cleanly into two populations:

1. **Real NBA/WNBA answers** (WEMBY, SPURS, BLOCK, SGA, CLARK, ACE, SKY…) — the wider sources
   landed. These clues are current, specific, and reference real recent events (the thobe, the
   Kornet block, the OKC series). **This is the win we were going for.**
2. **Garbage fill words** (SWB, OPELS, KUMOG, CRBCA, SYK, GUMOK, ARBCC, YPY, EHY, PGS…) — these
   aren't words or real abbreviations. The grid-fill algorithm emits them to complete the grid,
   and the clue generator then *fabricates* plausible-sounding NBA references for them
   ("SWB = Wemby's team" — the Spurs are SAS, not SWB). **These clues are confidently wrong and
   are the #1 quality problem.** No amount of prompt tuning fixes a clue for a non-word.

So as you rate: clues in the **Fill-word** sections are mostly there to confirm the pattern —
the real fix for those is upstream (grid fill / wordlist), which I've flagged as a follow-up
decision at the bottom. Focus your KEEP/FIX energy on the **Real-answer** sections.

---

## NBA — Grid A (publish 2026-06-02, "today")

### Real answers

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| A1 | WEMBY | wry | Showed up to Game 6 in a thobe, then had feelings about it. | great |
| A2 | SPURS | wry | Oklahoma City said goodbye in seven. | fix - doesn't realy make sense? "Oklahoma City said goodbye in seven"... and the answer is "spurs". there's a logical gap there|
| A3 | BLOCK | factual | Kornet's chasedown rejection in San Antonio, all over feeds yesterday. | great |
| A4 | SGA | discoursey | Foul hunter who somehow goes cold when the whistle stays in the pocket, OKC's guy | good |
| A5 | OKC | wry | Eliminated by Wemby, briefly. | good, kind of simple. |

### Fill words (pattern confirmation — clues are fabricated)

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| A6 | SWB | wry | Wemby's team, abbreviated like a bus pass. *(Spurs are SAS, not SWB)* | |
| A7 | OPELS | wry | German cars that, unlike the Thunder, still have a future. | |
| A8 | KUMOG | discoursey | Wemby crying after sending OKC home, clouds in the building fr | |
| A9 | CRBCA | factual | Spurs' path to the Finals ran through OKC, ended in five. | |
| A10 | SYK | discoursey | Chet's teammate who couldn't save OKC from Wemby's run, three letters | |

---

## NBA — Grid B (seed 2026-05-30)

### Real answers

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| B1 | SPURS | wry | Oklahoma City found out the hard way, 111-103. | |
| B2 | WEMBY | wry | Showed up to Game 6 in a thobe, left with the crowd's heart. | |
| B3 | BLOCK | wry | Kornet's gift to San Antonio, no wrapping required. | |
| B4 | SGA | wry | Thunder guard whose foul-drawing drew a Mike Greenberg monologue, not a compliment. | |
| B5 | OKC | discoursey | Thunder got bounced by Wemby's crew, rip to that run | |

### Fill words

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| B6 | SPELO | factual | San Antonio's arena, where the Spurs closed out OKC to reach the Finals. *(not a real arena)* | |
| B7 | GUMOK | discoursey | SGA and the boys, just eliminated by Wemby's Spurs, ouch. | |
| B8 | ARBCC | factual | OKC's home arena, where the Thunder's 2026 playoff run ended. *(not real)* | |
| B9 | SYK | discoursey | Dort's teammate who just helped send OKC home early, Shai's guy | |

---

## NBA — Grid C (seed 2026-05-28)

### Real / plausible answers

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| C1 | LLAMA | factual | Animal nickname for Cooper Flagg, top 2026 Draft prospect. | fix i've never heard of this nickname.  |
| C2 | LAMBS | wry | Silence of the ___, or how SGA's critics feel after he drops 35. | fix - silence of the lambs is not a feeling |
| C3 | STAMP | wry | What Wemby's ejection left on his playoff résumé. | weak answer |
| C4 | WEMBY | wry | Showed up to Game 6 in a thobe, then fouled out in spirit. | fix - how does 'thobe' relate to the spirit of fouling out |
| C5 | SAS | discoursey | Wemby's squad, getting cooked by OKC in the Semis rn | fix - too easy |
| C6 | ALL | wry | "___ of the above" for the OKC flopping debate, perhaps. | fix - horrible way too easy|

### Fill words

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| C7 | ANTES | discoursey | Buy-ins before the series gets real, basically | |
| C8 | INLAY | discoursey | Parquet floor detail that makes the hardwood actually look clean, tbh | |
| C9 | ISW | wry | Abbr. on a replay feed set to "No Spoilers," theoretically. | |
| C10 | YPY | factual | NBA app shorthand for the "hide results" toggle players and fans use during playoffs. *(invented)* | |

---

## WNBA — Grid D (publish 2026-06-02)

### Real answers

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| D1 | ACE | wry | Wilson's unofficial title, and a card worth keeping. | great - fantastic |
| D2 | CLARK | wry | She rides for Steph, apparently. | okay - kind of strange. didnt' know this|
| D3 | PULSE | wry | Gustafson checked Portland's, found it strong. | great |
| D4 | SKY | discoursey | Chi squad that's trying to figure out if they're real this season, tbh | sure|
| D5 | STRAY | factual | Off-script play, in basketball parlance. | fix - don't think 'STRAY' is correct|

### Fill words

| # | Answer | Voice | Clue | Verdict |
|---|--------|-------|------|---------|
| D6 | AUNTS | wry | Caitlin and Sabrina, to a new generation of hoop-obsessed kids. | |
| D7 | PGS | wry | Paige, Gustafson, and a third friend: abbr. | |
| D8 | EHY | discoursey | Paige to Castle after that Game 7, pure joy in that moment | |
| D9 | GNASH | discoursey | Gustafson holding back tears postgame, that interview had you like 😬 | |
| D10 | ESSAY | factual | Five-paragraph school assignment, for short. | |

---

## Cross-cutting questions for you

Mark a ✓ or write a note:

1. **Voice mix.** Across the real answers, is the wry/discoursey/factual ratio right, or do you
   want more of one? (Right now it leans wry.) → ____ the wry clues were good. i think i like this balance. 
2. **Recency references.** Clues lean *hard* on the current Spurs/OKC series and the thobe. Good
   (feels alive) or too repetitive across a single puzzle? → ____ too repetitive for sure. need more variety
3. **"discoursey" register.** The lowercase-no-punctuation "rip to that run / fr / tbh" style —
   keep as a flavor, dial back, or cut? → ____ i don't want discoursey "clues", but rather discoursey answers. not in style or tone but in content... "chalamet". 
4. **Factual clue dryness.** The factual ones on real answers (A3, C1) are tight. On fill words
   they invent fake arenas. Assuming we fix the fill problem, is the factual voice itself good? → factual ones are good. 

## The fill-word decision (follow-up, not a clue rating)

The fabricated clues all trace to one upstream cause: the grid contains non-words. Three ways to
attack it, roughly increasing effort — **tell me which to pursue and I'll spin it into its own task:**

- **(a) Bigger/cleaner wordlist** — feed the grid-fill more real short words/abbreviations so it
  rarely needs junk. Lowest effort, biggest single win. 
- **(b) "Honest fill" clue mode** — when an answer isn't a known word/NBA term, force a *non-NBA*
  dictionary-style clue (or a straight "abbr." style) instead of letting the model invent NBA
  lore. Medium effort; makes junk fill at least *honest*.
- **(c) Reject grids above a junk threshold** — re-roll the fill seed until the grid is mostly
  real words. Highest effort, best ceiling, risks no-puzzle days on hard grids.

My recommendation: **(a) first** (cheap, addresses root cause), then **(b)** as a safety net.

--- B! yes. doesn't have to be 100% NBA. actually, i think there are great quality ones to be had here. make the puzzle *mostly* basketball of course. but for filler words, do anything! any sort of NYT level and style crossword puzzle. no easy ones or freebees! try looking at a huge corpus of nyt mini and non-mini crossword clues and answers. 

*Generated from live Bedrock runs on 2026-06-02. Hand this back marked up and I'll tune the
prompt files + open the fill-word follow-up.*
