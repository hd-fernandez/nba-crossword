"use client";

import type { Entry, Puzzle } from "@/lib/puzzle";
import { configFor } from "@/lib/league";
import { entryNumberMap } from "@/lib/state";

interface ClueBarProps {
  puzzle: Puzzle;
  activeEntry: Entry | null;
}

/**
 * Shows the current entry's number, direction, and clue text.
 * e.g. "5 ACROSS — Visited TD Garden, scored 40, left."
 *
 * Themed by the puzzle's league: the entry tag picks up the league's accent
 * color (NBA red, WNBA orange) so the play surface reads as belonging to
 * that league even without looking at the URL.
 */
export function ClueBar({ puzzle, activeEntry }: ClueBarProps) {
  const accent = configFor(puzzle.league).theme.accent;

  if (!activeEntry) {
    return (
      <div
        role="region"
        aria-label="active clue"
        style={{
          background: "#f4f1ea",
          borderRadius: 8,
          padding: "12px 14px",
          fontSize: 14,
          minHeight: 44,
          color: "#6b6b6b",
          fontStyle: "italic",
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
        background: "#f4f1ea",
        borderRadius: 8,
        padding: "12px 14px",
        fontSize: 15,
        lineHeight: 1.4,
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
      }}
    >
      <span
        style={{
          flexShrink: 0,
          marginTop: 1,
          fontSize: 11,
          fontWeight: 700,
          color: accent,
          letterSpacing: "0.06em",
          padding: "2px 7px",
          background: "#fff",
          borderRadius: 4,
          border: `1px solid ${accent}33`,
        }}
        data-testid="clue-tag"
      >
        {number ?? "?"}
        {activeEntry.direction === "across" ? "A" : "D"}
      </span>
      <span
        style={{ flex: 1, color: "#1a1a1a" }}
        data-testid="clue-text"
      >
        <span
          style={{
            fontWeight: 600,
            marginRight: 6,
            letterSpacing: "0.02em",
            fontSize: 13,
            color: "#666",
            textTransform: "uppercase",
          }}
        >
          {number ?? "?"} {directionLabel}
        </span>
        {activeEntry.clue}
      </span>
    </div>
  );
}
