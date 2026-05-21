import { afterEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  buildEmojiGrid,
  buildShareText,
  formatElapsed,
  formatPuzzleDate,
  shareOrCopy,
} from "@/lib/share";
import { parsePuzzle, type Puzzle } from "@/lib/puzzle";
import { makeEmptyRevealed } from "@/lib/state";

const EXAMPLE_PATH = resolve(__dirname, "../../puzzles/nba/example.json");

function loadExamplePuzzle(): Puzzle {
  const raw = JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
  return parsePuzzle(raw);
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// formatElapsed
// ---------------------------------------------------------------------------

describe("formatElapsed", () => {
  it("formats sub-minute times with zero-padded seconds", () => {
    expect(formatElapsed(0)).toBe("0:00");
    expect(formatElapsed(1_000)).toBe("0:01");
    expect(formatElapsed(9_000)).toBe("0:09");
    expect(formatElapsed(59_999)).toBe("0:59");
  });

  it("rolls into minutes correctly", () => {
    expect(formatElapsed(60_000)).toBe("1:00");
    expect(formatElapsed(84_000)).toBe("1:24");
    expect(formatElapsed(125_500)).toBe("2:05");
  });

  it("clamps invalid values to 0:00", () => {
    expect(formatElapsed(-5)).toBe("0:00");
    expect(formatElapsed(NaN)).toBe("0:00");
    expect(formatElapsed(Infinity)).toBe("0:00");
  });
});

// ---------------------------------------------------------------------------
// formatPuzzleDate
// ---------------------------------------------------------------------------

describe("formatPuzzleDate", () => {
  it("formats valid ISO dates as 'MMM D'", () => {
    expect(formatPuzzleDate("2026-05-14")).toBe("May 14");
    expect(formatPuzzleDate("2026-01-01")).toBe("Jan 1");
    expect(formatPuzzleDate("2026-12-31")).toBe("Dec 31");
  });

  it("does not let timezone shift the day", () => {
    // The bug we're guarding against: `new Date("2026-05-14")` parses as
    // UTC midnight, which is May 13 in US/Eastern. Our parser must work
    // off the literal date string.
    expect(formatPuzzleDate("2026-05-14")).toBe("May 14");
  });

  it("echoes back unrecognized strings", () => {
    expect(formatPuzzleDate("not-a-date")).toBe("not-a-date");
    expect(formatPuzzleDate("2026-13-01")).toBe("2026-13-01");
  });
});

// ---------------------------------------------------------------------------
// buildEmojiGrid
// ---------------------------------------------------------------------------

describe("buildEmojiGrid", () => {
  it("emits ⬛ for blocks and 🟩 for clean letter cells", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    const grid = buildEmojiGrid(puzzle, revealed);
    // Row 0: SPAR + block
    expect(grid[0]).toEqual(["🟩", "🟩", "🟩", "🟩", "⬛"]);
    // Row 4: block + POSE
    expect(grid[4]).toEqual(["⬛", "🟩", "🟩", "🟩", "🟩"]);
  });

  it("emits 🟨 for revealed cells", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    revealed[1][2] = true;
    const grid = buildEmojiGrid(puzzle, revealed);
    expect(grid[1][2]).toBe("🟨");
    // Other letter cells stay 🟩
    expect(grid[1][0]).toBe("🟩");
  });

  it("emits all 🟨 for a fully-revealed puzzle (with blocks still ⬛)", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = puzzle.grid.cells.map((row) =>
      row.map((cell) => "answer" in cell),
    );
    const grid = buildEmojiGrid(puzzle, revealed);
    expect(grid[0]).toEqual(["🟨", "🟨", "🟨", "🟨", "⬛"]);
    expect(grid[4]).toEqual(["⬛", "🟨", "🟨", "🟨", "🟨"]);
  });
});

// ---------------------------------------------------------------------------
// buildShareText
// ---------------------------------------------------------------------------

describe("buildShareText", () => {
  it("includes title, date, time, grid, and attribution", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    const text = buildShareText(puzzle, 84_000, revealed);
    expect(text).toContain("The NBA Mini · May 15");
    expect(text).toContain("1:24");
    expect(text).toContain("nbamini.app");
    // Five emoji rows
    const emojiRows = text.split("\n").filter((l) => /^[🟩🟨⬛]+$/.test(l));
    expect(emojiRows).toHaveLength(5);
  });

  it("contains no answer letters or clue text", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    const text = buildShareText(puzzle, 0, revealed);
    // Letter answers must not appear
    for (const entry of puzzle.entries) {
      expect(text).not.toContain(entry.answer);
    }
    // Clue text must not appear
    for (const entry of puzzle.entries) {
      // Some clues are short — be safe with substring ≥ 10 chars
      const fragment = entry.clue.slice(0, 10);
      if (fragment.length >= 8) {
        expect(text).not.toContain(fragment);
      }
    }
  });

  it("clean solve produces a grid with only 🟩 and ⬛", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    const text = buildShareText(puzzle, 60_000, revealed);
    expect(text).not.toContain("🟨");
    expect(text).toContain("🟩");
    expect(text).toContain("⬛");
  });

  it("revealing one cell shows exactly one 🟨 in the share", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    revealed[2][2] = true;
    const text = buildShareText(puzzle, 60_000, revealed);
    const yellowCount = (text.match(/🟨/g) ?? []).length;
    expect(yellowCount).toBe(1);
  });

  it("fully-revealed solve shows all 🟨 (and ⬛ for blocks)", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = puzzle.grid.cells.map((row) =>
      row.map((cell) => "answer" in cell),
    );
    const text = buildShareText(puzzle, 60_000, revealed);
    expect(text).not.toContain("🟩");
    // 23 letter cells in the example (25 - 2 blocks)
    const yellowCount = (text.match(/🟨/g) ?? []).length;
    expect(yellowCount).toBe(23);
  });
});

// ---------------------------------------------------------------------------
// shareOrCopy
// ---------------------------------------------------------------------------

describe("shareOrCopy", () => {
  it("uses navigator.share when available", async () => {
    const share = vi.fn(async () => {});
    const writeText = vi.fn(async () => {});
    const result = await shareOrCopy("hello", {
      navigator: { share, clipboard: { writeText } },
    });
    expect(result).toBe("shared");
    expect(share).toHaveBeenCalledWith({ text: "hello" });
    expect(writeText).not.toHaveBeenCalled();
  });

  it("falls back to clipboard when navigator.share is missing", async () => {
    const writeText = vi.fn(async () => {});
    const result = await shareOrCopy("hello", {
      navigator: { clipboard: { writeText } },
    });
    expect(result).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("falls back to clipboard when navigator.share rejects (non-abort)", async () => {
    const share = vi.fn(async () => {
      throw new Error("oops");
    });
    const writeText = vi.fn(async () => {});
    const result = await shareOrCopy("hello", {
      navigator: { share, clipboard: { writeText } },
    });
    expect(result).toBe("copied");
    expect(writeText).toHaveBeenCalledWith("hello");
  });

  it("re-throws AbortError so the caller can no-op the user-cancel", async () => {
    const share = vi.fn(async () => {
      const e = new Error("user cancelled");
      e.name = "AbortError";
      throw e;
    });
    const writeText = vi.fn(async () => {});
    await expect(
      shareOrCopy("hello", {
        navigator: { share, clipboard: { writeText } },
      }),
    ).rejects.toMatchObject({ name: "AbortError" });
    expect(writeText).not.toHaveBeenCalled();
  });

  it("throws when neither share nor clipboard exist", async () => {
    await expect(shareOrCopy("hello", { navigator: {} })).rejects.toThrow(
      /no share or clipboard/i,
    );
  });
});
