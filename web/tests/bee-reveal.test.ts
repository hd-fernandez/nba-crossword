import { describe, expect, it } from "vitest";

import { parseBeePuzzle, scoreName, type BeePuzzle } from "@/lib/bee";
import {
  beeReducer,
  initialBeeState,
  isBeeSolved,
  scoreState,
  type BeeState,
} from "@/lib/bee-state";

// Names chosen so length-ascending reveal order is unambiguous and differs
// from both alphabetical-only and corpus order.
function makePuzzle(): BeePuzzle {
  return parseBeePuzzle({
    date: "2026-06-01",
    league: "nba",
    bee_number: 1,
    center_letter: "L",
    outer_letters: ["A", "B", "E", "N", "O", "R"],
    // Lengths: LOBO=4, ABEL=4, LEBRON=6, ALEBRON=7 (pangram).
    valid_names: ["LEBRON", "LOBO", "ABEL", "ALEBRON"],
    pangrams: ["ALEBRON"],
    tier_thresholds: {
      g_league_callup: 1,
      rookie: 5,
      sophomore: 12,
      vet: 22,
      all_star: 35,
      champion: 50,
      hall_of_famer: 70,
      goat: 100,
    },
    max_score: 100,
    generated_at: "2026-06-01T10:00:00.000Z",
  });
}

function applyReveals(puzzle: BeePuzzle, n: number): BeeState {
  const reduce = beeReducer(puzzle);
  let state = initialBeeState();
  for (let i = 0; i < n; i++) {
    state = reduce(state, { type: "revealWord" });
  }
  return state;
}

describe("beeReducer revealWord", () => {
  it("reveals shortest-first, ties broken alphabetically", () => {
    const puzzle = makePuzzle();
    // Order should be: ABEL (4, alpha before LOBO), LOBO (4), LEBRON (6),
    // ALEBRON (7).
    const reduce = beeReducer(puzzle);
    let state = initialBeeState();

    state = reduce(state, { type: "revealWord" });
    expect(state.found[0]).toBe("ABEL");

    state = reduce(state, { type: "revealWord" });
    expect(state.found[0]).toBe("LOBO");

    state = reduce(state, { type: "revealWord" });
    expect(state.found[0]).toBe("LEBRON");

    state = reduce(state, { type: "revealWord" });
    expect(state.found[0]).toBe("ALEBRON");
  });

  it("emits 'revealed' feedback with the name and points", () => {
    const puzzle = makePuzzle();
    const state = applyReveals(puzzle, 1);
    expect(state.lastFeedback).toMatchObject({
      kind: "revealed",
      name: "ABEL",
      pointsGained: scoreName("ABEL", false),
      isPangram: false,
    });
  });

  it("flags a revealed pangram", () => {
    const puzzle = makePuzzle();
    const state = applyReveals(puzzle, 4); // 4th reveal is ALEBRON
    expect(state.lastFeedback).toMatchObject({
      kind: "revealed",
      name: "ALEBRON",
      isPangram: true,
    });
  });

  it("scores a reveal exactly like a normal find", () => {
    const puzzle = makePuzzle();
    const state = applyReveals(puzzle, 2); // ABEL + LOBO
    expect(scoreState(puzzle, state)).toBe(
      scoreName("ABEL", false) + scoreName("LOBO", false),
    );
  });

  it("skips already-found names", () => {
    const puzzle = makePuzzle();
    const reduce = beeReducer(puzzle);
    let state = initialBeeState();
    // Manually find LOBO first.
    state = { ...state, entry: "LOBO" };
    state = reduce(state, { type: "submit" });
    expect(state.found).toContain("LOBO");
    // Reveal should now skip LOBO and surface ABEL (next shortest unfound).
    state = reduce(state, { type: "revealWord" });
    expect(state.found[0]).toBe("ABEL");
  });

  it("clears any in-progress entry on reveal", () => {
    const puzzle = makePuzzle();
    const reduce = beeReducer(puzzle);
    let state = reduce(initialBeeState(), { type: "type", letter: "L" });
    expect(state.entry).toBe("L");
    state = reduce(state, { type: "revealWord" });
    expect(state.entry).toBe("");
  });

  it("revealing everything solves the puzzle", () => {
    const puzzle = makePuzzle();
    const state = applyReveals(puzzle, 4);
    expect(isBeeSolved(puzzle, state)).toBe(true);
  });

  it("reveal past the end is a safe no-op with 'allFound' feedback", () => {
    const puzzle = makePuzzle();
    const reduce = beeReducer(puzzle);
    let state = applyReveals(puzzle, 4);
    const before = state.found.length;
    state = reduce(state, { type: "revealWord" });
    expect(state.found.length).toBe(before);
    expect(state.lastFeedback).toMatchObject({ kind: "allFound" });
  });
});
