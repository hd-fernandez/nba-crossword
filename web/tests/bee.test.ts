import { describe, expect, it } from "vitest";

import {
  BeePuzzleSchema,
  TierThresholdsSchema,
  parseBeePuzzle,
  scoreName,
  tierForScore,
  type TierThresholds,
} from "@/lib/bee";

function makeThresholds(overrides: Partial<TierThresholds> = {}): TierThresholds {
  return {
    g_league_callup: 1,
    rookie: 5,
    sophomore: 12,
    vet: 22,
    all_star: 35,
    champion: 50,
    hall_of_famer: 70,
    goat: 100,
    ...overrides,
  };
}

function makePuzzle(overrides: Record<string, unknown> = {}) {
  return {
    date: "2026-05-22",
    league: "nba",
    bee_number: 1,
    center_letter: "L",
    outer_letters: ["A", "B", "E", "N", "O", "R"],
    valid_names: ["LEBRON", "LOBO", "ALEBRON"],
    pangrams: ["ALEBRON"],
    tier_thresholds: makeThresholds(),
    max_score: 20,
    generated_at: "2026-05-22T10:00:00.000Z",
    ...overrides,
  };
}

describe("TierThresholdsSchema", () => {
  it("accepts a well-ordered ascending set ending at 100", () => {
    expect(() => TierThresholdsSchema.parse(makeThresholds())).not.toThrow();
  });

  it("rejects out-of-order thresholds", () => {
    expect(() =>
      TierThresholdsSchema.parse(makeThresholds({ rookie: 30, sophomore: 10 })),
    ).toThrow(/ascending/);
  });

  it("rejects a top tier that isn't 100", () => {
    expect(() =>
      TierThresholdsSchema.parse(makeThresholds({ goat: 95 })),
    ).toThrow(/100/);
  });
});

describe("BeePuzzleSchema (structural)", () => {
  it("round-trips a valid puzzle", () => {
    const raw = makePuzzle();
    const parsed = parseBeePuzzle(raw);
    expect(parsed.center_letter).toBe("L");
    expect(parsed.valid_names).toContain("LEBRON");
  });

  it("rejects when outer_letters has the wrong count", () => {
    expect(() =>
      parseBeePuzzle(makePuzzle({ outer_letters: ["A", "B", "C", "D", "E"] })),
    ).toThrow(/6 entries/);
  });

  it("rejects when center letter appears in outer letters", () => {
    expect(() =>
      parseBeePuzzle(
        makePuzzle({ outer_letters: ["L", "A", "B", "E", "N", "O"] }),
      ),
    ).toThrow(/center_letter/);
  });

  it("rejects duplicate outer letters", () => {
    expect(() =>
      parseBeePuzzle(
        makePuzzle({ outer_letters: ["A", "A", "B", "E", "N", "O"] }),
      ),
    ).toThrow(/distinct/);
  });

  it("rejects a valid_names entry missing the center letter", () => {
    expect(() =>
      parseBeePuzzle(makePuzzle({ valid_names: ["LEBRON", "OBORE"] })),
    ).toThrow(/center letter/);
  });

  it("rejects a valid_names entry using off-board letters", () => {
    expect(() =>
      parseBeePuzzle(makePuzzle({ valid_names: ["LEBRON", "LZONE"] })),
    ).toThrow(/not on the board/);
  });

  it("rejects a pangram not in valid_names", () => {
    expect(() =>
      parseBeePuzzle(makePuzzle({ pangrams: ["LANEBOR"] })),
    ).toThrow(/not in valid_names/);
  });

  it("rejects a pangram that doesn't use all 7 letters", () => {
    expect(() =>
      parseBeePuzzle(
        makePuzzle({
          valid_names: ["LEBRON", "LOBO"],
          pangrams: ["LOBO"],
        }),
      ),
    ).toThrow(/all 7 letters/);
  });

  it("rejects unknown top-level fields (strict mode)", () => {
    const raw = makePuzzle({ surprise: "field" });
    expect(() => parseBeePuzzle(raw)).toThrow();
  });

  it("rejects an unknown league", () => {
    expect(() => parseBeePuzzle(makePuzzle({ league: "g_league" }))).toThrow();
  });

  it("allows an empty valid_names list (boundary case)", () => {
    const parsed = parseBeePuzzle(
      makePuzzle({ valid_names: [], pangrams: [] }),
    );
    expect(parsed.valid_names).toEqual([]);
  });
});

describe("scoreName", () => {
  it("4-letter name = 1 point", () => {
    expect(scoreName("LOBO", false)).toBe(1);
  });

  it("5-letter name = 5 points", () => {
    expect(scoreName("CURRY", false)).toBe(5);
  });

  it("6-letter name = 6 points", () => {
    expect(scoreName("LEBRON", false)).toBe(6);
  });

  it("pangram bonus = letter count + 7", () => {
    expect(scoreName("ALEBRON", true)).toBe(7 + 7);
    expect(scoreName("LEBRON", true)).toBe(6 + 7);
  });

  it("under-4-letter names score 0", () => {
    expect(scoreName("LEB", false)).toBe(0);
    expect(scoreName("L", false)).toBe(0);
  });
});

describe("tierForScore", () => {
  const t = makeThresholds();
  const max = 100;

  it("returns null when score is below the lowest threshold", () => {
    expect(tierForScore(0, t, max)).toBeNull();
  });

  it("returns the highest tier whose threshold has been crossed", () => {
    // 22% of 100 = 22 → exactly the 'vet' threshold
    expect(tierForScore(22, t, max)).toBe("vet");
    // Just below sophomore (12%)
    expect(tierForScore(11, t, max)).toBe("rookie");
  });

  it("returns 'goat' at exactly max_score", () => {
    expect(tierForScore(max, t, max)).toBe("goat");
  });

  it("scales thresholds with a non-100 max_score", () => {
    // 50% of 200 = 100 → 'champion'
    expect(tierForScore(100, t, 200)).toBe("champion");
  });

  it("returns 'g_league_callup' just past the lowest threshold", () => {
    // 1% of 100 = 1; score 1 hits g_league_callup, score 0 returns null
    expect(tierForScore(1, t, max)).toBe("g_league_callup");
    expect(tierForScore(0, t, max)).toBeNull();
  });
});
