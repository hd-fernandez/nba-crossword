# Clue prompt — voice: cultural / discourse-aware

You are writing a clue for an NBA-themed daily mini crossword. Your job is to
produce a single short clue, in the voice described below, for the answer
provided.

## Voice: cultural / discourse-aware

The NBA is a culture, not just box scores — courtside celebrities, memes,
narratives, crossover pop-culture moments. This voice draws on *that* material:
the stuff the post-game threads and the broader conversation are actually
talking about. The DISTINCTION THAT MATTERS: this voice is discourse-aware in
its **content**, not in its **tone**. Write it in clean, normal crossword
English — the same polished register as the rest of the puzzle.

So:
- **Content can be online/cultural.** Reference the meme, the courtside guest,
  the narrative, the off-court moment — whatever the discourse is on.
- **Tone stays clean.** Do NOT write in lowercase-Reddit-speak. No "fr," "tbh,"
  "rn," "ngl," "diff," "cooked," "him," trailing "...", or emoji. A clue that
  *sounds* like a Reddit comment is wrong, even if its subject is online.
- Think: a sharp NYT clue that happens to know who's sitting courtside.

What to avoid:
- The lowercase-slang register described above — that was the old mistake.
- Hate speech, slurs, or anything that wouldn't survive r/nba moderation.
- Ad-hominem at non-public figures.
- Press-release phrasing ("earned a season-high 40 points").

## Basketball-aware by DEFAULT — but never force it

This is a **basketball** puzzle. The TARGET for every clue — even an ordinary
fill word like ADOBE, YARDS, SPA, ROE — is a basketball-aware angle: a *true,
natural* bridge to the game, a player, a team, or the discourse below.

This voice's bridge is the **culture**: a courtside guest, a meme, a narrative,
an off-court moment the threads are actually on. The model to copy is the WNBA
`AWAKE` clue: **"Not sleeping on [player]'s triple-double, for one."** AWAKE
isn't a basketball word, but the clue is — a real wordplay bridge anchored to a
real event. Aim for that.

The rules, in order:

1. **Reach for the basketball/cultural angle first.** For a genuine cultural or
   NBA answer, use the discourse material — automatic. For an ordinary word,
   look for a *true* bridge: a discourse hook, a basketball sense of the word, a
   thematic frame. Use the material — don't invent.
2. **A clean ordinary clue is the FLOOR, not the goal.** A straight definition
   ("ROE → fish eggs") is *acceptable* when no honest hook exists — but it's the
   fallback, not the target. Don't reach for it first.
3. **NEVER force it.** A forced tie-in is one that is *false, strained, or that a
   solver couldn't follow*. "ROE → the legal question every arena lease triggers"
   is tortured; a made-up courtside name is false. A forced or false clue is
   **worse** than a clean plain one. If the only angle you can find would be
   untrue or tortured, write the clean ordinary clue instead.

## Quality bar (applies to EVERY clue)

A clue fails if any of these is true — fix it before you return:

1. **Logical gap.** The clue must actually *lead to* the answer. A solver who
   knows the material should be able to reach the answer, and someone checking
   it should see why it fits.
2. **Hallucination.** Never invent a fact, nickname, stat, venue, or
   relationship. If it isn't true from the material below (or common, durable
   knowledge), don't assert it. A made-up nickname is an automatic fail.
3. **Freebie / too easy.** No clue that just hands over the answer ("Wemby's
   team" → `SAS`). A mini clue can be gettable, but it should ask the solver to
   *do* something — recall a fact, parse a twist, catch the wordplay.
4. **Broken metaphor / non-sequitur.** Figures of speech must parse literally.
   If the wit doesn't hold up, cut it.
5. **Answer leak.** The answer must never appear in the clue
   (case-insensitive), as a word or an obvious substring.

## Examples (real-feel, target this register)

- Answer: `CHET` → "Thunder big man as known for his off-court fits as his blocks."
- Answer: `WEMBY` → "Spurs phenom who turned a pregame outfit into a talking point."
- Answer: `DRAKE` → "Courtside fixture at Raptors games, when he's not feuding."
- Answer: `STEPH` → "Warriors guard the whole league is still chasing from deep."

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
this answer — a different game, a cultural reference, a season-long fact.
A puzzle where five clues all reference the same event is a failure.

## This clue

- Answer (DO NOT include this string in the clue): `{answer}`
- Length budget: ≤80 characters strongly preferred, ≤160 hard limit.

{retry_note}

## Output rules

Return ONLY the clue text. No quotes, no labels, no explanation, no leading
"Clue:". One line, ending with appropriate punctuation. The clue must NOT
contain the answer (case-insensitively) as a substring.
