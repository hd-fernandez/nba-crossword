import { z } from "zod";

import { withBasePath } from "./base-path";

export const GRID_SIZE = 5;

export const VoiceSchema = z.enum(["wry", "discoursey", "factual"]);
export type Voice = z.infer<typeof VoiceSchema>;

export const DirectionSchema = z.enum(["across", "down"]);
export type Direction = z.infer<typeof DirectionSchema>;

export const LeagueSchema = z.enum(["nba", "wnba"]);
export type League = z.infer<typeof LeagueSchema>;

const LetterCellSchema = z
  .object({ answer: z.string().regex(/^[A-Z]$/) })
  .strict();

const BlockCellSchema = z.object({ block: z.literal(true) }).strict();

export const CellSchema = z.union([LetterCellSchema, BlockCellSchema]);
export type Cell = z.infer<typeof CellSchema>;

export const GridSchema = z
  .object({
    size: z.literal(GRID_SIZE),
    cells: z.array(z.array(CellSchema)),
  })
  .strict()
  .refine((g) => g.cells.length === GRID_SIZE, {
    message: `grid must have ${GRID_SIZE} rows`,
  })
  .refine((g) => g.cells.every((row) => row.length === GRID_SIZE), {
    message: `every row must have ${GRID_SIZE} cells`,
  });
export type Grid = z.infer<typeof GridSchema>;

export const EntrySchema = z
  .object({
    id: z.string(),
    direction: DirectionSchema,
    row: z.number().int().min(0).max(GRID_SIZE - 1),
    col: z.number().int().min(0).max(GRID_SIZE - 1),
    answer: z
      .string()
      .regex(/^[A-Z]+$/)
      .min(2)
      .max(GRID_SIZE),
    clue: z.string().min(1).max(160),
    voice: VoiceSchema,
  })
  .strict();
export type Entry = z.infer<typeof EntrySchema>;

const RawPuzzleSchema = z
  .object({
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    // The day the underlying games were played. Usually date - 1, but can be
    // older when the league didn't play yesterday. Optional for back-compat
    // with puzzles authored before this field existed.
    slate_date: z
      .string()
      .regex(/^\d{4}-\d{2}-\d{2}$/)
      .optional(),
    // Which league this puzzle belongs to. Defaults to "nba" for back-compat
    // with v0 fixtures written before the multi-league split. New puzzles
    // always set it explicitly.
    league: LeagueSchema.default("nba"),
    // Sequential count since launch, independent per league.
    puzzle_number: z.number().int().min(1),
    grid: GridSchema,
    entries: z.array(EntrySchema),
    season_context_version: z.string(),
    generated_at: z.string().datetime({ offset: true }),
    model: z.string(),
  })
  .strict();

function isLetterCell(cell: Cell): cell is { answer: string } {
  return "answer" in cell;
}

export const PuzzleSchema = RawPuzzleSchema.superRefine((puzzle, ctx) => {
  const cells = puzzle.grid.cells;
  const seenStarts = new Set<string>();
  const acrossCovered = new Set<string>();
  const downCovered = new Set<string>();

  const inBounds = (r: number, c: number) =>
    r >= 0 && r < GRID_SIZE && c >= 0 && c < GRID_SIZE;

  for (const entry of puzzle.entries) {
    const startKey = `${entry.row},${entry.col},${entry.direction}`;
    if (seenStarts.has(startKey)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `duplicate entry start at ${startKey}`,
      });
      return;
    }
    seenStarts.add(startKey);

    for (let i = 0; i < entry.answer.length; i++) {
      const r = entry.row + (entry.direction === "down" ? i : 0);
      const c = entry.col + (entry.direction === "across" ? i : 0);
      if (!inBounds(r, c)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `entry ${entry.id} (${entry.answer}) runs off the grid at (${r},${c})`,
        });
        return;
      }
      const cell = cells[r][c];
      if (!isLetterCell(cell)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `entry ${entry.id} (${entry.answer}) crosses block at (${r},${c})`,
        });
        return;
      }
      const expected = entry.answer[i];
      if (cell.answer !== expected) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: `entry ${entry.id} letter ${i} expects '${expected}', grid has '${cell.answer}' at (${r},${c})`,
        });
        return;
      }
      if (entry.direction === "across") {
        acrossCovered.add(`${r},${c}`);
      } else {
        downCovered.add(`${r},${c}`);
      }
    }

    const beforeR = entry.row - (entry.direction === "down" ? 1 : 0);
    const beforeC = entry.col - (entry.direction === "across" ? 1 : 0);
    if (inBounds(beforeR, beforeC) && isLetterCell(cells[beforeR][beforeC])) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `entry ${entry.id} does not start at the head of its run`,
      });
      return;
    }

    const endI = entry.answer.length;
    const afterR = entry.row + (entry.direction === "down" ? endI : 0);
    const afterC = entry.col + (entry.direction === "across" ? endI : 0);
    if (inBounds(afterR, afterC) && isLetterCell(cells[afterR][afterC])) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `entry ${entry.id} does not end at the tail of its run`,
      });
      return;
    }
  }

  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      if (isLetterCell(cells[r][c])) {
        if (!acrossCovered.has(`${r},${c}`)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `cell (${r},${c}) is not part of any across entry`,
          });
        }
        if (!downCovered.has(`${r},${c}`)) {
          ctx.addIssue({
            code: z.ZodIssueCode.custom,
            message: `cell (${r},${c}) is not part of any down entry`,
          });
        }
      }
    }
  }
});

export type Puzzle = z.infer<typeof PuzzleSchema>;

export function parsePuzzle(raw: unknown): Puzzle {
  return PuzzleSchema.parse(raw);
}

/**
 * Today's date in US/Eastern, formatted YYYY-MM-DD.
 *
 * The NBA day boundary lines up with ET (per U4 / R6). We do this client-side
 * with Intl.DateTimeFormat so it tracks the user's wall-clock perception of
 * "today's puzzle" regardless of their device locale.
 */
export function todayInEastern(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/**
 * Fetch a puzzle JSON for the given league + date (default today).
 *
 * Returns `null` on 404 — the frontend treats that as the dormant "no puzzle
 * today" state (R6 / AE3). Any other failure (malformed JSON, schema
 * violation, network error) throws so the caller can surface a real error.
 *
 * Puzzles are served as static files at `/puzzles/<league>/<date>.json`.
 * The canonical source is the repo-root `puzzles/<league>/` directory;
 * `scripts/sync-puzzles.mjs` copies that into `web/public/puzzles/` on
 * `predev` and `prebuild`.
 */
export async function fetchPuzzle(
  league: League,
  date: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<Puzzle | null> {
  const res = await fetchImpl(withBasePath(`/puzzles/${league}/${date}.json`), {
    cache: "no-store",
  });
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error(
      `failed to fetch ${league} puzzle for ${date}: HTTP ${res.status}`,
    );
  }
  const raw = await res.json();
  return parsePuzzle(raw);
}

/**
 * The puzzle index written by `scripts/sync-puzzles.mjs`. Lists every
 * available puzzle date for a league, newest first, plus the latest.
 */
const PuzzleIndexSchema = z.object({
  dates: z.array(z.string().regex(/^\d{4}-\d{2}-\d{2}$/)),
  latest: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).nullable(),
});
export type PuzzleIndex = z.infer<typeof PuzzleIndexSchema>;

/**
 * Read a league's puzzle index. Returns null if the index is missing or
 * malformed — callers treat that as "no fallback available."
 */
export async function fetchPuzzleIndex(
  league: League,
  fetchImpl: typeof fetch = fetch,
): Promise<PuzzleIndex | null> {
  try {
    const res = await fetchImpl(withBasePath(`/puzzles/${league}/index.json`), {
      cache: "no-store",
    });
    if (!res.ok) return null;
    const parsed = PuzzleIndexSchema.safeParse(await res.json());
    if (!parsed.success) {
      // A malformed index is an operational problem, not a normal 404. Warn so
      // it's debuggable instead of silently collapsing to "no fallback."
      console.warn(`[puzzle] malformed ${league} index.json`, parsed.error);
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

/**
 * The result of resolving which puzzle to show: the puzzle itself, plus
 * whether it's actually today's or a fallback to the most recent one.
 */
export interface ResolvedPuzzle {
  puzzle: Puzzle;
  date: string;
  isToday: boolean;
}

/**
 * Fetch the puzzle to display for a league: today's if it exists, otherwise
 * the most recent available puzzle (per the index). Returns null only when
 * the league has no puzzles at all.
 *
 * This is what keeps the app from showing a dead "no puzzle today" page when
 * the daily generator hasn't produced today's puzzle yet (off-day, cron lag,
 * or — during local demos — no live cron at all). Today always wins when
 * present; the fallback is the graceful degradation.
 */
export async function fetchLatestPuzzle(
  league: League,
  today: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<ResolvedPuzzle | null> {
  const todays = await fetchPuzzle(league, today, fetchImpl);
  if (todays) return { puzzle: todays, date: today, isToday: true };

  const index = await fetchPuzzleIndex(league, fetchImpl);
  if (!index) return null;
  // Candidate fallbacks: every non-future date, newest first. We walk them in
  // order rather than trusting only the newest — if the newest indexed file
  // 404s (index/file skew, deploy race, a pruned file) we fall through to the
  // next one instead of collapsing to a dead "no puzzle" page while older
  // puzzles still exist.
  const candidates = index.dates
    .filter((d) => d <= today)
    .sort()
    .reverse();
  for (const date of candidates) {
    const fallback = await fetchPuzzle(league, date, fetchImpl);
    if (fallback) return { puzzle: fallback, date, isToday: false };
  }
  return null;
}

/**
 * Back-compat shim — the v1 page-level fetch was league-naive. New callers
 * should use `fetchPuzzle(league, date)` directly. This wrapper defaults to
 * NBA so existing tests / call sites keep working through the v2 transition.
 */
export async function fetchTodayPuzzle(
  date: string = todayInEastern(),
  fetchImpl: typeof fetch = fetch,
): Promise<Puzzle | null> {
  return fetchPuzzle("nba", date, fetchImpl);
}
