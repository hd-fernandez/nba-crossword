"use client";

import type { Entry, Puzzle } from "@/lib/puzzle";
import { entryNumberMap } from "@/lib/state";

interface ClueBarProps {
  puzzle: Puzzle;
  activeEntry: Entry | null;
}

/**
 * Shows the current entry's number, direction, and clue text.
 * e.g. "5 ACROSS — Visited TD Garden, scored 40, left."
 *
 * If no entry is active (e.g., before any cell is selected, or on the
 * dormant state) we render an empty placeholder so the layout doesn't jump.
 */
export function ClueBar({ puzzle, activeEntry }: ClueBarProps) {
  if (!activeEntry) {
    return (
      <div
        role="region"
        aria-label="active clue"
        style={{
          background: "#f1efe8",
          borderRadius: 6,
          padding: "10px 12px",
          fontSize: 14,
          minHeight: 40,
          color: "#6b6b6b",
        }}
      >
        Select a cell to see its clue.
      </div>
    );
  }

  const numbers = entryNumberMap(puzzle.grid);
  const number = numbers.get(`${activeEntry.row},${activeEntry.col}`);
  const directionLabel = activeEntry.direction.toUpperCase();

  return (
    <div
      role="region"
      aria-label="active clue"
      data-testid="clue-bar"
      style={{
        background: "#f1efe8",
        borderRadius: 6,
        padding: "10px 12px",
        fontSize: 14,
        display: "flex",
        alignItems: "center",
        gap: 10,
      }}
    >
      <span
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: "#c8102e",
          letterSpacing: "0.05em",
        }}
        data-testid="clue-tag"
      >
        {number ?? "?"}
        {activeEntry.direction === "across" ? "A" : "D"}
      </span>
      <span style={{ flex: 1 }} data-testid="clue-text">
        <strong style={{ marginRight: 6 }}>
          {number ?? "?"} {directionLabel}
        </strong>
        — {activeEntry.clue}
      </span>
    </div>
  );
}
