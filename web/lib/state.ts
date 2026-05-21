/**
 * Local solve state for the daily puzzle.
 *
 * Designed as a pure reducer + selectors so the Grid/ClueBar components stay
 * dumb and the test surface is just data-in / data-out. No persistence yet
 * (U12 will introduce localStorage).
 *
 * "Direction" semantics: at any time we have a current selected cell and a
 * current direction. The active *entry* is whichever entry contains that
 * cell and runs in that direction. NYT-mini conventions:
 *   - Typing a letter advances the cursor in the current direction.
 *   - Backspace clears the current cell; if it was already empty, it
 *     retreats first and clears that one.
 *   - Arrow keys: a perpendicular arrow flips direction first, then moves.
 *   - Space toggles direction at the current cell.
 *   - Tab jumps to the start of the next entry (wraps).
 *   - Tapping a black cell is a no-op; tapping the current cell flips
 *     direction.
 *   - Cursor never lands on a block; arrow movement skips over blocks.
 */

import {
  type Cell,
  type Direction,
  type Entry,
  type Grid,
  type Puzzle,
  GRID_SIZE,
} from "./puzzle";

export type CellPos = { row: number; col: number };

export interface SolveState {
  selectedCell: CellPos | null;
  direction: Direction;
  /** 5x5; null for blocks and for empty letter cells. */
  letters: (string | null)[][];
  /**
   * 5x5; true at letter cells that were filled by a reveal action (letter,
   * word, or puzzle). Always false at blocks. Persists across further edits
   * — once revealed, the share grid still shows the cell as 🟨.
   */
  revealed: boolean[][];
  /**
   * Timer anchor. `startedAt` is the epoch-ms when the running interval
   * started; null while paused (or before first input). `accumulatedMs` is
   * the elapsed time accrued during prior running intervals. Live elapsed =
   * accumulatedMs + (now - startedAt) when running, else accumulatedMs.
   */
  startedAt: number | null;
  accumulatedMs: number;
  /**
   * Set once when the puzzle is first detected complete (every letter cell
   * matches the answer). Idempotent — further edits to `letters` don't
   * unset or re-trigger it.
   */
  finishedAt: number | null;
}

export type SolveAction =
  | { type: "selectCell"; row: number; col: number }
  | { type: "setDirection"; direction: Direction }
  | { type: "toggleDirection" }
  | { type: "enterLetter"; letter: string }
  | { type: "backspace" }
  | { type: "arrow"; dRow: number; dCol: number }
  | { type: "nextEntry" }
  | { type: "previousEntry" }
  | { type: "startTimer"; now: number }
  | { type: "tick" }
  | { type: "pauseTimer"; now: number }
  | { type: "resumeTimer"; now: number }
  | { type: "revealLetter" }
  | { type: "revealWord" }
  | { type: "revealPuzzle" };

// ---------------------------------------------------------------------------
// Cell helpers
// ---------------------------------------------------------------------------

export function isBlock(cell: Cell): boolean {
  return "block" in cell;
}

export function isLetter(cell: Cell): cell is { answer: string } {
  return "answer" in cell;
}

export function inBounds(row: number, col: number): boolean {
  return row >= 0 && row < GRID_SIZE && col >= 0 && col < GRID_SIZE;
}

export function getCell(grid: Grid, row: number, col: number): Cell | null {
  if (!inBounds(row, col)) return null;
  return grid.cells[row][col];
}

// ---------------------------------------------------------------------------
// Entry numbering
//
// A cell starts an entry iff it's a letter cell AND either (a) it's at the
// edge or the cell above it is a block (starts a down entry) or (b) similarly
// to the left (starts an across entry). Numbers are assigned in scan order
// (top→bottom, left→right) — one number per starting cell, possibly shared
// between an across and a down entry at the same coords.
// ---------------------------------------------------------------------------

export interface EntryNumber {
  row: number;
  col: number;
  number: number;
  startsAcross: boolean;
  startsDown: boolean;
}

export function computeEntryNumbers(grid: Grid): EntryNumber[] {
  const result: EntryNumber[] = [];
  let next = 1;

  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      const cell = grid.cells[r][c];
      if (!isLetter(cell)) continue;

      const leftCell = c > 0 ? grid.cells[r][c - 1] : null;
      const aboveCell = r > 0 ? grid.cells[r - 1][c] : null;

      const startsAcross =
        (leftCell === null || isBlock(leftCell)) &&
        c + 1 < GRID_SIZE &&
        isLetter(grid.cells[r][c + 1]);
      const startsDown =
        (aboveCell === null || isBlock(aboveCell)) &&
        r + 1 < GRID_SIZE &&
        isLetter(grid.cells[r + 1][c]);

      if (startsAcross || startsDown) {
        result.push({ row: r, col: c, number: next, startsAcross, startsDown });
        next += 1;
      }
    }
  }
  return result;
}

/** Map "<row>,<col>" -> entry number (only set for cells that start an entry). */
export function entryNumberMap(grid: Grid): Map<string, number> {
  const map = new Map<string, number>();
  for (const en of computeEntryNumbers(grid)) {
    map.set(`${en.row},${en.col}`, en.number);
  }
  return map;
}

// ---------------------------------------------------------------------------
// Active entry resolution
// ---------------------------------------------------------------------------

/**
 * Walk the grid from a cell in the given direction until we find the start
 * of the run that contains this cell. Returns the (row, col) of the start
 * letter cell. Assumes (row, col) is a letter cell.
 */
export function findEntryStart(
  grid: Grid,
  row: number,
  col: number,
  direction: Direction,
): CellPos {
  let r = row;
  let c = col;
  if (direction === "across") {
    while (c > 0) {
      const prev = grid.cells[r][c - 1];
      if (isBlock(prev)) break;
      c -= 1;
    }
  } else {
    while (r > 0) {
      const prev = grid.cells[r - 1][c];
      if (isBlock(prev)) break;
      r -= 1;
    }
  }
  return { row: r, col: c };
}

/**
 * Find the puzzle entry that contains (row, col) running in `direction`.
 * Returns null if the cell is a block or doesn't have a run in that
 * direction (e.g., a single-cell run, which shouldn't happen in valid puzzles
 * but we don't crash on it).
 */
export function findActiveEntry(
  puzzle: Puzzle,
  row: number,
  col: number,
  direction: Direction,
): Entry | null {
  const cell = getCell(puzzle.grid, row, col);
  if (!cell || !isLetter(cell)) return null;
  const start = findEntryStart(puzzle.grid, row, col, direction);
  return (
    puzzle.entries.find(
      (e) =>
        e.direction === direction &&
        e.row === start.row &&
        e.col === start.col,
    ) ?? null
  );
}

// ---------------------------------------------------------------------------
// Initial state
// ---------------------------------------------------------------------------

/** Build a 5x5 letters grid initialized to null at every cell (blocks and empties alike). */
export function makeEmptyLetters(grid: Grid): (string | null)[][] {
  return grid.cells.map((row) => row.map(() => null));
}

/** Build a 5x5 boolean grid initialized to false at every cell. */
export function makeEmptyRevealed(grid: Grid): boolean[][] {
  return grid.cells.map((row) => row.map(() => false));
}

/** Find the first letter cell scanning left-to-right, top-to-bottom. */
export function findFirstLetterCell(grid: Grid): CellPos | null {
  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      if (isLetter(grid.cells[r][c])) return { row: r, col: c };
    }
  }
  return null;
}

export function initialState(puzzle: Puzzle): SolveState {
  const first = findFirstLetterCell(puzzle.grid);
  return {
    selectedCell: first,
    direction: "across",
    letters: makeEmptyLetters(puzzle.grid),
    revealed: makeEmptyRevealed(puzzle.grid),
    startedAt: null,
    accumulatedMs: 0,
    finishedAt: null,
  };
}

/** Whether every letter cell in `letters` matches the puzzle's answer key. */
export function isPuzzleSolved(puzzle: Puzzle, letters: (string | null)[][]): boolean {
  for (let r = 0; r < GRID_SIZE; r++) {
    for (let c = 0; c < GRID_SIZE; c++) {
      const cell = puzzle.grid.cells[r][c];
      if (!isLetter(cell)) continue;
      if (letters[r][c] !== cell.answer) return false;
    }
  }
  return true;
}

/** Live elapsed time, accounting for whether the timer is running. */
export function elapsedMs(state: SolveState, now: number): number {
  if (state.finishedAt !== null) {
    // After finish, freeze the displayed time at the moment of completion.
    if (state.startedAt !== null) {
      return state.accumulatedMs + (state.finishedAt - state.startedAt);
    }
    return state.accumulatedMs;
  }
  if (state.startedAt === null) return state.accumulatedMs;
  return state.accumulatedMs + (now - state.startedAt);
}

// ---------------------------------------------------------------------------
// Movement helpers
// ---------------------------------------------------------------------------

/**
 * Advance one step in `direction` from (row, col), skipping blocks. Returns
 * null if no further letter cell is reachable in this run. (We do NOT wrap
 * past blocks — once you hit a block, the run ends.)
 */
export function nextCellInRun(
  grid: Grid,
  row: number,
  col: number,
  direction: Direction,
): CellPos | null {
  const r = row + (direction === "down" ? 1 : 0);
  const c = col + (direction === "across" ? 1 : 0);
  if (!inBounds(r, c)) return null;
  const cell = grid.cells[r][c];
  if (isBlock(cell)) return null;
  return { row: r, col: c };
}

export function prevCellInRun(
  grid: Grid,
  row: number,
  col: number,
  direction: Direction,
): CellPos | null {
  const r = row - (direction === "down" ? 1 : 0);
  const c = col - (direction === "across" ? 1 : 0);
  if (!inBounds(r, c)) return null;
  const cell = grid.cells[r][c];
  if (isBlock(cell)) return null;
  return { row: r, col: c };
}

/**
 * Move one step in (dRow, dCol) skipping blocks; if the immediate neighbor is
 * a block, keep stepping in the same direction until a letter or out of
 * bounds. Returns null if no letter cell is reachable.
 */
export function stepSkippingBlocks(
  grid: Grid,
  row: number,
  col: number,
  dRow: number,
  dCol: number,
): CellPos | null {
  let r = row + dRow;
  let c = col + dCol;
  while (inBounds(r, c)) {
    const cell = grid.cells[r][c];
    if (isLetter(cell)) return { row: r, col: c };
    r += dRow;
    c += dCol;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Entry sequencing (Tab / Shift-Tab)
// ---------------------------------------------------------------------------

/**
 * Sort entries in a stable "next entry" order: by entry-number, then
 * across-before-down at the same start cell. This matches the visual ordering
 * in a clue list.
 */
export function sortedEntriesForNav(puzzle: Puzzle): Entry[] {
  const numbers = entryNumberMap(puzzle.grid);
  return [...puzzle.entries].sort((a, b) => {
    const aNum = numbers.get(`${a.row},${a.col}`) ?? 999;
    const bNum = numbers.get(`${b.row},${b.col}`) ?? 999;
    if (aNum !== bNum) return aNum - bNum;
    if (a.direction === b.direction) return 0;
    return a.direction === "across" ? -1 : 1;
  });
}

/** Iterate the (row, col) cells covered by an entry. */
function* entryCells(entry: Entry): Generator<{ row: number; col: number }> {
  for (let i = 0; i < entry.answer.length; i++) {
    yield {
      row: entry.row + (entry.direction === "down" ? i : 0),
      col: entry.col + (entry.direction === "across" ? i : 0),
    };
  }
}

/** True when every cell of the entry has a letter (correct or not). */
export function entryCellsAllFilled(
  entry: Entry,
  letters: (string | null)[][],
): boolean {
  for (const { row, col } of entryCells(entry)) {
    if (!letters[row][col]) return false;
  }
  return true;
}

/** First empty cell inside the entry, or null if it's already full. */
export function firstEmptyCellInEntry(
  entry: Entry,
  letters: (string | null)[][],
): { row: number; col: number } | null {
  for (const cell of entryCells(entry)) {
    if (!letters[cell.row][cell.col]) return cell;
  }
  return null;
}

/**
 * Next entry after `current` in nav order. Prefers entries in the *same*
 * direction first (NYT-mini behavior: finishing an across entry takes you
 * to the next across, not to a down), then wraps to perpendicular entries
 * only after all same-direction entries are exhausted. Returns null if
 * there's only one entry.
 */
export function nextEntryAfter(puzzle: Puzzle, current: Entry): Entry | null {
  const entries = sortedEntriesForNav(puzzle);
  if (entries.length <= 1) return null;

  const sameDir = entries.filter((e) => e.direction === current.direction);
  const idxSameDir = sameDir.findIndex(
    (e) => e.row === current.row && e.col === current.col,
  );

  // If there's another entry in the same direction, use it.
  if (idxSameDir !== -1 && idxSameDir < sameDir.length - 1) {
    return sameDir[idxSameDir + 1];
  }

  // Otherwise, hand off to the first entry in the perpendicular direction.
  const otherDir = entries.find((e) => e.direction !== current.direction);
  return otherDir ?? null;
}

// ---------------------------------------------------------------------------
// Reducer
// ---------------------------------------------------------------------------

/**
 * After every action that might affect `letters`, check whether the puzzle
 * is now complete and stamp `finishedAt` exactly once. Once set, this never
 * un-sets — further edits don't re-trigger or reset the finish.
 *
 * If `finishedAt` is set this call also freezes the running timer at the
 * completion moment by folding `(finishedAt - startedAt)` into
 * `accumulatedMs` and clearing `startedAt`. That way a tick after finish
 * doesn't keep advancing the displayed time.
 */
function withFinishCheck(
  puzzle: Puzzle,
  state: SolveState,
  now: number,
): SolveState {
  if (state.finishedAt !== null) return state; // idempotent
  if (!isPuzzleSolved(puzzle, state.letters)) return state;
  let accumulatedMs = state.accumulatedMs;
  let startedAt: number | null = state.startedAt;
  if (startedAt !== null) {
    accumulatedMs = accumulatedMs + (now - startedAt);
    startedAt = null;
  }
  return {
    ...state,
    finishedAt: now,
    startedAt,
    accumulatedMs,
  };
}

export function solveReducer(
  puzzle: Puzzle,
  /**
   * Time source. Defaults to `Date.now`; tests can inject a deterministic
   * clock without monkey-patching globals. Called once per action that
   * needs a timestamp (timer transitions and finish stamping).
   */
  nowFn: () => number = () => Date.now(),
): (state: SolveState, action: SolveAction) => SolveState {
  return (state, action) => {
    switch (action.type) {
      case "selectCell": {
        const cell = getCell(puzzle.grid, action.row, action.col);
        if (!cell || !isLetter(cell)) return state; // blacks are no-ops
        // tapping the same cell flips direction
        if (
          state.selectedCell &&
          state.selectedCell.row === action.row &&
          state.selectedCell.col === action.col
        ) {
          return {
            ...state,
            direction: state.direction === "across" ? "down" : "across",
          };
        }
        return {
          ...state,
          selectedCell: { row: action.row, col: action.col },
        };
      }

      case "setDirection":
        if (state.direction === action.direction) return state;
        return { ...state, direction: action.direction };

      case "toggleDirection":
        return {
          ...state,
          direction: state.direction === "across" ? "down" : "across",
        };

      case "enterLetter": {
        if (!state.selectedCell) return state;
        const letter = action.letter.toUpperCase();
        if (!/^[A-Z]$/.test(letter)) return state;
        const { row, col } = state.selectedCell;
        const newLetters = state.letters.map((r) => r.slice());
        newLetters[row][col] = letter;
        const next = nextCellInRun(puzzle.grid, row, col, state.direction);
        const now = nowFn();
        // Auto-start the timer on first input. If already running, leave it.
        const startedAt =
          state.startedAt === null && state.finishedAt === null
            ? now
            : state.startedAt;

        // NYT-mini auto-advance: when this keystroke fills the last empty cell
        // of the current entry, jump to the start of the next entry. We jump
        // on "filled" not "correct" so a typo'd entry still moves you forward
        // — the user can come back and fix it later.
        let selectedCell = next ?? state.selectedCell;
        let direction = state.direction;
        const activeEntry = findActiveEntry(puzzle, row, col, state.direction);
        if (activeEntry) {
          const entryFilled = entryCellsAllFilled(activeEntry, newLetters);
          if (entryFilled) {
            const nextEntry = nextEntryAfter(puzzle, activeEntry);
            if (nextEntry) {
              const firstEmpty = firstEmptyCellInEntry(nextEntry, newLetters);
              selectedCell = firstEmpty ?? { row: nextEntry.row, col: nextEntry.col };
              direction = nextEntry.direction;
            }
          }
        }

        const advanced: SolveState = {
          ...state,
          letters: newLetters,
          selectedCell,
          direction,
          startedAt,
        };
        return withFinishCheck(puzzle, advanced, now);
      }

      case "backspace": {
        if (!state.selectedCell) return state;
        const { row, col } = state.selectedCell;
        const newLetters = state.letters.map((r) => r.slice());

        if (newLetters[row][col]) {
          // current has a letter — clear it, stay put
          newLetters[row][col] = null;
          return { ...state, letters: newLetters };
        }
        // current is empty — retreat and clear that one
        const prev = prevCellInRun(puzzle.grid, row, col, state.direction);
        if (!prev) return state;
        newLetters[prev.row][prev.col] = null;
        return { ...state, letters: newLetters, selectedCell: prev };
      }

      case "arrow": {
        if (!state.selectedCell) return state;
        const { row, col } = state.selectedCell;
        const isHorizontal = action.dCol !== 0;
        const arrowDir: Direction = isHorizontal ? "across" : "down";

        // If user presses a perpendicular arrow, flip direction first.
        if (state.direction !== arrowDir) {
          return { ...state, direction: arrowDir };
        }
        const next = stepSkippingBlocks(
          puzzle.grid,
          row,
          col,
          action.dRow,
          action.dCol,
        );
        if (!next) return state;
        return { ...state, selectedCell: next };
      }

      case "nextEntry":
      case "previousEntry": {
        const entries = sortedEntriesForNav(puzzle);
        if (entries.length === 0 || !state.selectedCell) return state;
        const current = findActiveEntry(
          puzzle,
          state.selectedCell.row,
          state.selectedCell.col,
          state.direction,
        );
        const idx = current
          ? entries.findIndex(
              (e) =>
                e.row === current.row &&
                e.col === current.col &&
                e.direction === current.direction,
            )
          : -1;
        const delta = action.type === "nextEntry" ? 1 : -1;
        const nextIdx = (idx + delta + entries.length) % entries.length;
        const target = entries[nextIdx];
        return {
          ...state,
          selectedCell: { row: target.row, col: target.col },
          direction: target.direction,
        };
      }

      case "startTimer": {
        // Idempotent: only sets startedAt if not already running.
        if (state.startedAt !== null || state.finishedAt !== null) return state;
        return { ...state, startedAt: action.now };
      }

      case "tick": {
        // No-op state change — used solely as a re-render trigger when the
        // Timer component wants to refresh the displayed elapsed value.
        // Returning the same reference would skip re-renders, so we return
        // a shallow copy. Most consumers should rely on Timer's own
        // setInterval rather than dispatching this.
        return { ...state };
      }

      case "pauseTimer": {
        if (state.startedAt === null) return state; // already paused
        if (state.finishedAt !== null) return state; // finished — no-op
        const accumulatedMs = state.accumulatedMs + (action.now - state.startedAt);
        return { ...state, startedAt: null, accumulatedMs };
      }

      case "resumeTimer": {
        // Resume only resumes if the timer was previously started (i.e.,
        // there is accumulated time OR the user has typed at least one
        // letter). Don't auto-start before first input.
        if (state.startedAt !== null) return state; // already running
        if (state.finishedAt !== null) return state; // finished — no-op
        if (state.accumulatedMs === 0) return state; // never started
        return { ...state, startedAt: action.now };
      }

      case "revealLetter": {
        if (!state.selectedCell) return state;
        const { row, col } = state.selectedCell;
        const cell = getCell(puzzle.grid, row, col);
        if (!cell || !isLetter(cell)) return state;
        const newLetters = state.letters.map((r) => r.slice());
        const newRevealed = state.revealed.map((r) => r.slice());
        newLetters[row][col] = cell.answer;
        newRevealed[row][col] = true;
        const now = nowFn();
        const startedAt =
          state.startedAt === null && state.finishedAt === null
            ? now
            : state.startedAt;
        return withFinishCheck(
          puzzle,
          { ...state, letters: newLetters, revealed: newRevealed, startedAt },
          now,
        );
      }

      case "revealWord": {
        if (!state.selectedCell) return state;
        const entry = findActiveEntry(
          puzzle,
          state.selectedCell.row,
          state.selectedCell.col,
          state.direction,
        );
        if (!entry) return state;
        const newLetters = state.letters.map((r) => r.slice());
        const newRevealed = state.revealed.map((r) => r.slice());
        for (let i = 0; i < entry.answer.length; i++) {
          const r = entry.row + (entry.direction === "down" ? i : 0);
          const c = entry.col + (entry.direction === "across" ? i : 0);
          newLetters[r][c] = entry.answer[i];
          newRevealed[r][c] = true;
        }
        const now = nowFn();
        const startedAt =
          state.startedAt === null && state.finishedAt === null
            ? now
            : state.startedAt;
        return withFinishCheck(
          puzzle,
          { ...state, letters: newLetters, revealed: newRevealed, startedAt },
          now,
        );
      }

      case "revealPuzzle": {
        const newLetters = state.letters.map((r) => r.slice());
        const newRevealed = state.revealed.map((r) => r.slice());
        for (let r = 0; r < GRID_SIZE; r++) {
          for (let c = 0; c < GRID_SIZE; c++) {
            const cell = puzzle.grid.cells[r][c];
            if (!isLetter(cell)) continue;
            // Only mark cells the user hadn't already filled correctly.
            // (If they filled it correctly themselves, no need to flag it
            // as revealed in the share grid.)
            if (newLetters[r][c] !== cell.answer) {
              newLetters[r][c] = cell.answer;
              newRevealed[r][c] = true;
            }
          }
        }
        const now = nowFn();
        const startedAt =
          state.startedAt === null && state.finishedAt === null
            ? now
            : state.startedAt;
        return withFinishCheck(
          puzzle,
          { ...state, letters: newLetters, revealed: newRevealed, startedAt },
          now,
        );
      }
    }
  };
}
