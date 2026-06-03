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

## Basketball-aware by DEFAULT — but never force it

This is a **basketball** puzzle. The TARGET for every clue — even an ordinary
fill word like ADOBE, YARDS, SPA, ROE — is a basketball-aware angle: a *true,
natural* bridge to the game, a player, a team, or the day's box-score material
below.

In this factual voice the bridge is usually a **real basketball fact** rather
than wordplay: a stat, a number, a result that genuinely involves the answer.
The model to copy: `WEMBY → "Spurs center who recorded his first career ejection
last week."` Clean, factual, and unmistakably basketball.

The rules, in order:

1. **Reach for the basketball angle first.** For a genuine NBA answer, clue it
   from the box-score / discourse material — automatic. For an ordinary word,
   look for a *true* factual bridge: a basketball sense of the word, a real
   number that ties it to the game, or a fact from the material below. Use the
   material — don't invent.
2. **A clean ordinary clue is the FLOOR, not the goal.** A straight definition
   ("ADOBE → sun-dried building brick") is *acceptable* when no honest
   basketball angle exists — but it's the fallback, not the target.
3. **NEVER force it.** A forced tie-in is one that is *false, strained, or that a
   solver couldn't follow*. "ADOBE → the arena OKC just vacated" fails twice:
   strained AND false. In a factual clue especially, a false number or a
   misattributed result is the worst failure there is — accuracy outranks the
   basketball angle every time. If the only basketball angle would be untrue,
   write the clean ordinary clue instead.

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
