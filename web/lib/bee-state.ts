/**
 * Reducer + helpers for the Bee solve experience.
 *
 * State owns: the current entry being formed, the set of found names, the
 * accumulated score. Pure functions, no DOM.
 */

import { scoreName, type BeePuzzle } from "./bee";

export type EntryFeedback =
  | { kind: "ok"; pointsGained: number; isPangram: boolean }
  | { kind: "revealed"; name: string; pointsGained: number; isPangram: boolean }
  | { kind: "tooShort" }
  | { kind: "missingCenter" }
  | { kind: "badLetters" }
  | { kind: "notInList" }
  | { kind: "alreadyFound" }
  | { kind: "allFound" };

export interface BeeState {
  entry: string;
  /** Found names in chronological discovery order (most recent first). */
  found: string[];
  /** Latest feedback from a submit attempt — drives the toast/animation. */
  lastFeedback: EntryFeedback | null;
  /** Tick that bumps every action so React can key off it for animations. */
  feedbackKey: number;
}

export type BeeAction =
  | { type: "tap"; letter: string }
  | { type: "type"; letter: string }
  | { type: "delete" }
  | { type: "shuffle" }
  | { type: "submit" }
  | { type: "clearEntry" }
  | { type: "revealWord" };

export function initialBeeState(): BeeState {
  return {
    entry: "",
    found: [],
    lastFeedback: null,
    feedbackKey: 0,
  };
}

/** True when every cell in the puzzle is found. */
export function isBeeSolved(puzzle: BeePuzzle, state: BeeState): boolean {
  if (puzzle.valid_names.length === 0) return false;
  return state.found.length >= puzzle.valid_names.length;
}

/** Score the user's current state. Pangrams get the bonus. */
export function scoreState(puzzle: BeePuzzle, state: BeeState): number {
  const pangramSet = new Set(puzzle.pangrams);
  let score = 0;
  for (const name of state.found) {
    score += scoreName(name, pangramSet.has(name));
  }
  return score;
}

/**
 * The reducer factory pattern matches the crossword side: pass the puzzle
 * up front so the action handler doesn't have to ferry it through every
 * dispatch payload.
 */
export function beeReducer(puzzle: BeePuzzle) {
  const validSet = new Set(puzzle.valid_names);
  const pangramSet = new Set(puzzle.pangrams);
  const board = new Set([puzzle.center_letter, ...puzzle.outer_letters]);
  // Reveal order: shortest first, ties broken alphabetically so the sequence
  // is deterministic and stable across reveals.
  const revealOrder = [...puzzle.valid_names].sort(
    (a, b) => a.length - b.length || (a < b ? -1 : a > b ? 1 : 0),
  );

  return function reduce(state: BeeState, action: BeeAction): BeeState {
    switch (action.type) {
      case "tap":
      case "type": {
        const letter = action.letter.toUpperCase();
        if (!/^[A-Z]$/.test(letter)) return state;
        if (!board.has(letter)) {
          // Typing an off-board letter is a no-op rather than an error so
          // the user doesn't have to be surgical with their input.
          return state;
        }
        // Soft cap at 15 chars to prevent runaway entries; longer than any
        // realistic name and bounds the visible entry bar.
        if (state.entry.length >= 15) return state;
        return { ...state, entry: state.entry + letter };
      }

      case "delete": {
        if (state.entry.length === 0) return state;
        return { ...state, entry: state.entry.slice(0, -1) };
      }

      case "clearEntry": {
        if (state.entry.length === 0) return state;
        return { ...state, entry: "" };
      }

      case "shuffle": {
        // Pure-data only; the visual shuffle of outer letters is owned by
        // the renderer (a `shuffleKey` ref bumped by the same dispatch).
        return state;
      }

      case "revealWord": {
        // Reveal the shortest not-yet-found name (ties alphabetical). Scores
        // it exactly like a normal find — a reveal is a hint, not a separate
        // currency. Clears any in-progress entry so the board reads cleanly.
        const foundSet = new Set(state.found);
        const next = revealOrder.find((name) => !foundSet.has(name));
        if (next === undefined) {
          return {
            ...state,
            lastFeedback: { kind: "allFound" },
            feedbackKey: state.feedbackKey + 1,
          };
        }
        const isPangram = pangramSet.has(next);
        const points = scoreName(next, isPangram);
        return {
          ...state,
          entry: "",
          found: [next, ...state.found],
          lastFeedback: {
            kind: "revealed",
            name: next,
            pointsGained: points,
            isPangram,
          },
          feedbackKey: state.feedbackKey + 1,
        };
      }

      case "submit": {
        const word = state.entry;
        let feedback: EntryFeedback;
        if (word.length < 4) {
          feedback = { kind: "tooShort" };
        } else if (!word.includes(puzzle.center_letter)) {
          feedback = { kind: "missingCenter" };
        } else if (![...word].every((ch) => board.has(ch))) {
          feedback = { kind: "badLetters" };
        } else if (state.found.includes(word)) {
          feedback = { kind: "alreadyFound" };
        } else if (!validSet.has(word)) {
          feedback = { kind: "notInList" };
        } else {
          const isPangram = pangramSet.has(word);
          const points = scoreName(word, isPangram);
          return {
            ...state,
            entry: "",
            found: [word, ...state.found],
            lastFeedback: { kind: "ok", pointsGained: points, isPangram },
            feedbackKey: state.feedbackKey + 1,
          };
        }
        // Negative-feedback path: keep the entry so the user can edit it
        // (matches NYT Bee behavior on `notInList`).
        return {
          ...state,
          lastFeedback: feedback,
          feedbackKey: state.feedbackKey + 1,
        };
      }
    }
  };
}
