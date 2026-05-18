/**
 * Spoiler-free share text generator for the NBA Mini.
 *
 * Output shape (NYT-mini / Wordle inspired, our own identity):
 *
 *   The NBA Mini · May 14
 *   1:24
 *
 *   🟩🟩🟩🟩⬛
 *   🟩🟩🟨🟩🟩
 *   🟩🟩🟩🟩🟩
 *   🟩🟩🟩🟩🟩
 *   ⬛🟩🟩🟩🟩
 *
 *   nbamini.app
 *
 * Emoji mapping:
 *   🟩 = clean letter cell (user got it without a reveal)
 *   🟨 = letter cell that was revealed at any point
 *   ⬛ = block cell (always — keeps the grid silhouette intact)
 *
 * We never include answer letters or clue text. The shape of the puzzle
 * (which cells are blocks) is leaked, which matches NYT mini behavior.
 */

import type { Puzzle } from "./puzzle";
import { isLetter } from "./state";

/** Format an integer milliseconds value as "M:SS". Negative or NaN → "0:00". */
export function formatElapsed(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) ms = 0;
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

const MONTH_ABBREVS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * Format a puzzle date string ("YYYY-MM-DD") as "MMM D".
 *
 * Parses the components manually (no `new Date(...)`) to avoid timezone
 * shenanigans — the puzzle's date is the *NBA day* the puzzle is for, not a
 * local-wall-clock instant.
 */
export function formatPuzzleDate(date: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return date; // unrecognized format — best-effort echo back
  const month = parseInt(m[2], 10);
  const day = parseInt(m[3], 10);
  if (month < 1 || month > 12) return date;
  return `${MONTH_ABBREVS[month - 1]} ${day}`;
}

export type ShareEmoji = "🟩" | "🟨" | "⬛";

/**
 * Build the 5×5 emoji rows for a finished puzzle.
 *
 * `revealed[r][c]` should be true iff the user used a reveal (letter / word
 * / puzzle) on that cell. Block cells are emitted as ⬛ regardless of the
 * revealed map.
 */
export function buildEmojiGrid(
  puzzle: Puzzle,
  revealed: boolean[][],
): ShareEmoji[][] {
  return puzzle.grid.cells.map((row, r) =>
    row.map((cell, c) => {
      if (!isLetter(cell)) return "⬛" as const;
      return revealed[r][c] ? ("🟨" as const) : ("🟩" as const);
    }),
  );
}

/**
 * Compose the full share-text string. Pure function — easy to test. The
 * UI layer is responsible for getting it onto the user's clipboard or into
 * the Web Share API.
 *
 * Multiline format (a trailing newline is intentionally omitted):
 *
 *   The NBA Mini · {date}
 *   {time}
 *
 *   {grid…}
 *
 *   nbamini.app
 */
export function buildShareText(
  puzzle: Puzzle,
  elapsedMs: number,
  revealed: boolean[][],
): string {
  const grid = buildEmojiGrid(puzzle, revealed)
    .map((row) => row.join(""))
    .join("\n");
  const dateLabel = formatPuzzleDate(puzzle.date);
  const timeLabel = formatElapsed(elapsedMs);
  return [
    `The NBA Mini · ${dateLabel}`,
    timeLabel,
    "",
    grid,
    "",
    "nbamini.app",
  ].join("\n");
}

/**
 * Best-effort share. Tries the Web Share API first; falls back to writing
 * the share text to the clipboard. Returns the channel that succeeded so
 * the caller can show an appropriate confirmation ("Copied!" vs.
 * the native share sheet handling its own UX).
 *
 * Throws on hard failure (no clipboard support, both APIs unavailable).
 */
export type ShareResult = "shared" | "copied";

export async function shareOrCopy(
  text: string,
  /** For tests: inject window-equivalent to avoid global mutation pain. */
  win: {
    navigator?: {
      share?: (data: { text: string }) => Promise<void>;
      clipboard?: { writeText: (s: string) => Promise<void> };
    };
  } = typeof window !== "undefined" ? window : ({} as never),
): Promise<ShareResult> {
  const nav = win.navigator;
  if (nav && typeof nav.share === "function") {
    try {
      await nav.share({ text });
      return "shared";
    } catch (err) {
      // User-cancel on the native sheet rejects with AbortError; fall back
      // to clipboard so they still get something useful. Other errors also
      // fall through.
      if ((err as { name?: string })?.name === "AbortError") {
        // User explicitly cancelled — don't auto-copy. Re-throw so callers
        // can show no-op feedback.
        throw err;
      }
    }
  }
  if (nav?.clipboard && typeof nav.clipboard.writeText === "function") {
    await nav.clipboard.writeText(text);
    return "copied";
  }
  throw new Error("no share or clipboard API available");
}
