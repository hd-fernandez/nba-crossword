import { z } from "zod";

export const GRID_SIZE = 5;

export const VoiceSchema = z.enum(["wry", "discoursey", "factual"]);
export type Voice = z.infer<typeof VoiceSchema>;

export const DirectionSchema = z.enum(["across", "down"]);
export type Direction = z.infer<typeof DirectionSchema>;

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
