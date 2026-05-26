import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildBeeShareText,
  formatBeeDate,
  shareOrCopyBee,
} from "@/lib/bee-share";
import type { BeePuzzle, TierThresholds } from "@/lib/bee";

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

function makePuzzle(overrides: Partial<BeePuzzle> = {}): BeePuzzle {
  return {
    date: "2026-05-26",
    league: "nba",
    bee_number: 42,
    center_letter: "L",
    outer_letters: ["A", "B", "E", "N", "O", "R"],
    valid_names: ["LEBRON", "LOBO", "ALEBRON"],
    pangrams: ["ALEBRON"],
    tier_thresholds: makeThresholds(),
    max_score: 30,
    generated_at: "2026-05-26T10:00:00.000Z",
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("formatBeeDate", () => {
  it("formats ISO date as 'Month D'", () => {
    expect(formatBeeDate("2026-05-26")).toBe("May 26");
    expect(formatBeeDate("2026-12-01")).toBe("December 1");
  });
});

describe("buildBeeShareText", () => {
  it("includes league, date, bee number, tier, score, and URL", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle(),
      score: 24,
      foundCount: 2,
    });
    expect(text).toContain("NBA Bee #42");
    expect(text).toContain("May 26");
    // 24 / 30 = 80% → clears 70% (Hall of Famer) but not 100% (GOAT).
    expect(text).toContain("Hall of Famer");
    expect(text).toContain("2 / 3 names");
    expect(text).toContain("24 pts");
    expect(text).toContain("nbamini.app/nba/bee");
  });

  it("uses 👑 GOAT emoji at max score", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle(),
      score: 30,
      foundCount: 3,
    });
    expect(text).toContain("👑");
    expect(text).toContain("GOAT");
  });

  it("shows Undrafted at score 0", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle(),
      score: 0,
      foundCount: 0,
    });
    expect(text).toContain("Undrafted");
  });

  it("uses /bee path for combined league", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle({ league: "combined" }),
      score: 10,
      foundCount: 1,
    });
    expect(text).toContain("Hoops Bee");
    expect(text).toContain("nbamini.app/bee");
    expect(text).not.toContain("/combined/bee");
  });

  it("uses /wnba/bee for WNBA league", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle({ league: "wnba" }),
      score: 10,
      foundCount: 1,
    });
    expect(text).toContain("WNBA Bee");
    expect(text).toContain("nbamini.app/wnba/bee");
  });

  it("does not leak any valid_names or pangrams in the share text", () => {
    const text = buildBeeShareText({
      puzzle: makePuzzle(),
      score: 30,
      foundCount: 3,
    });
    expect(text).not.toContain("LEBRON");
    expect(text).not.toContain("ALEBRON");
    expect(text).not.toContain("LOBO");
  });
});

describe("shareOrCopyBee", () => {
  it("calls navigator.share when available", async () => {
    const share = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { share });
    const result = await shareOrCopyBee("hello");
    expect(result).toBe("shared");
    expect(share).toHaveBeenCalledWith({ text: "hello" });
  });

  it("falls back to clipboard when share is missing", async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const result = await shareOrCopyBee("hello");
    expect(result).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("returns 'unsupported' when neither API is available", async () => {
    vi.stubGlobal("navigator", {});
    const result = await shareOrCopyBee("hello");
    expect(result).toBe("unsupported");
  });

  it("rethrows AbortError so callers can detect user cancel", async () => {
    const share = vi.fn(async () => {
      throw new DOMException("user cancelled", "AbortError");
    });
    vi.stubGlobal("navigator", { share });
    await expect(shareOrCopyBee("hello")).rejects.toThrow();
  });

  it("falls back to clipboard on non-AbortError share failure", async () => {
    const share = vi.fn(async () => {
      throw new Error("some other failure");
    });
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal("navigator", { share, clipboard: { writeText } });
    const result = await shareOrCopyBee("hello");
    expect(result).toBe("copied");
    expect(writeText).toHaveBeenCalled();
  });
});
