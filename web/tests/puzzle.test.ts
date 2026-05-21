import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { parsePuzzle, PuzzleSchema } from "@/lib/puzzle";

const EXAMPLE_PATH = resolve(__dirname, "../../puzzles/nba/example.json");

function loadExample(): Record<string, unknown> {
  return JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
}

describe("PuzzleSchema", () => {
  it("round-trips the example puzzle", () => {
    const raw = loadExample();
    const puzzle = parsePuzzle(raw);
    expect(puzzle.date).toBe("2026-05-15");
    expect(puzzle.grid.size).toBe(5);
    expect(puzzle.entries).toHaveLength(10);
  });

  it("rejects a non-5x5 grid", () => {
    const raw = loadExample() as { grid: { cells: unknown[] } };
    raw.grid.cells.pop();
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects a row that is not 5 wide", () => {
    const raw = loadExample() as { grid: { cells: unknown[][] } };
    raw.grid.cells[0].pop();
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects an entry whose letters do not match the grid", () => {
    const raw = loadExample() as { entries: Array<{ answer: string }> };
    raw.entries[0].answer = "STAR";
    expect(() => parsePuzzle(raw)).toThrow(/expects/);
  });

  it("rejects a cell with both 'answer' and 'block'", () => {
    const raw = loadExample() as {
      grid: { cells: Array<Array<Record<string, unknown>>> };
    };
    raw.grid.cells[0][0] = { answer: "S", block: true };
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects an unknown field at the top level", () => {
    const raw = loadExample() as Record<string, unknown>;
    raw.extra_field = "nope";
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects an invalid voice", () => {
    const raw = loadExample() as { entries: Array<{ voice: string }> };
    raw.entries[0].voice = "snarky";
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects a lowercase answer", () => {
    const raw = loadExample() as { entries: Array<{ answer: string }> };
    raw.entries[0].answer = "spar";
    expect(() => parsePuzzle(raw)).toThrow();
  });

  it("rejects when a letter cell is uncovered down-wise", () => {
    const raw = loadExample() as { entries: Array<{ id: string }> };
    raw.entries = raw.entries.filter((e) => e.id !== "1D");
    expect(() => parsePuzzle(raw)).toThrow(/down entry/);
  });

  it("safeParse surfaces the shape of validation issues", () => {
    const raw = loadExample() as { entries: Array<{ answer: string }> };
    raw.entries[0].answer = "STAR";
    const result = PuzzleSchema.safeParse(raw);
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.length).toBeGreaterThan(0);
    }
  });
});
