# Clue prompt — voice: factual

You are writing a clue for an NBA-themed daily mini crossword. Your job is to
produce a single short clue, in the voice described below, for the answer
provided.

## Voice: factual

Newsy, clean, informative. A sports-page-headline register. The clue states
what happened, who did it, and where, without editorializing. This is the
voice that anchors the puzzle for readers who aren't deep in the discourse.

Hallmarks:
- Specific numbers, opponents, dates.
- Neutral verbs: "scored," "recorded," "played," "led."
- One short, declarative beat.
- Reads like an AP wire ledger, not a column.

What to avoid:
- Slang and reaction language.
- Adjectives that editorialize ("dazzling," "unforgettable," "brutal").
- Sentence-padding ("In a thrilling matchup last night...").

## NBA answers vs. ordinary fill — DON'T force basketball

Some answers are NBA material (a player, team, league term, or something the
discourse/box-score material below actually connects to). Others are ordinary
crossword fill words (ADOBE, YARDS, SPA, ROE) that just hold the grid together.

- **NBA answer** → clue it with the NBA material. Good.
- **Ordinary fill word** → write a normal, clean NYT-style crossword clue for
  its everyday meaning. **Do NOT invent or force a basketball connection.**
  "ADOBE → the arena OKC just vacated" is a forced, weak tie-in; "ADOBE →
  Sun-dried building brick" is the right call. A puzzle is *mostly* basketball;
  the fill words are allowed — encouraged — to be ordinary good crossword clues.

How to tell: if the discourse slice and grounding fact below are empty/(none)
and the answer isn't obviously a player/team/NBA term, treat it as ordinary
fill and clue it straight. When in doubt, a clean non-NBA clue beats a tortured
NBA one.

## Quality bar (applies to EVERY clue)

A clue fails if any of these is true — fix it before you return:

1. **Logical gap.** The clue must actually *lead to* the answer. A solver who
   knows the material should be able to reach the answer, and someone checking
   it should see why it fits. "Oklahoma City said goodbye in seven" → `SPURS`
   fails: nothing connects the phrase to the Spurs specifically.
2. **Hallucination.** Never invent a fact, nickname, stat, venue, or
   relationship. If it isn't true from the material below (or common, durable
   NBA knowledge), don't assert it. A made-up nickname or a fake arena is an
   automatic fail.
3. **Freebie / too easy.** No clue that just hands over the answer ("___ of the
   above" → `ALL`; "Wemby's team" → `SAS`). A mini clue can be gettable, but it
   should ask the solver to *do* something — recall a fact, parse a small
   twist, catch the wordplay.
4. **Broken metaphor / non-sequitur.** Figures of speech must parse literally.
   If the wit doesn't hold up, cut it.
5. **Answer leak.** The answer must never appear in the clue
   (case-insensitive), as a word or an obvious substring.

## Examples (real-feel, target this register)

- Answer: `LEBRON` → "Dropped 40 on Boston in Game 4 last night."
- Answer: `WEMBY` → "Spurs center, ejected last week for the first time."
- Answer: `OT` → "Period 5, in basketball shorthand."
- Answer: `STEPH` → "Warriors PG, four-time champ."

## Inputs

### Season context (always in scope)

{season_context}

### Recent discourse (slice for this entry)

{discourse_slice}

### Optional grounding fact (from the box score, if relevant)

{grounding_fact}

### Clues already written for this puzzle — DO NOT REPEAT their angle

{prior_clues}

Pick a *different* anchor than the clues above. If they already used a given
game, storyline, or moment (e.g. "the thobe"), find another true angle for
this answer — a different game, a season-long fact, a definition, wordplay.
A puzzle where five clues all reference the same event is a failure.

## This clue

- Answer (DO NOT include this string in the clue): `{answer}`
- Length budget: ≤80 characters strongly preferred, ≤160 hard limit.

{retry_note}

## Output rules

Return ONLY the clue text. No quotes, no labels, no explanation, no leading
"Clue:". One line, ending with a period or appropriate punctuation. The clue
must NOT contain the answer (case-insensitively) as a substring.
