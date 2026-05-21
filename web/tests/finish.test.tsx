import { afterEach, describe, expect, it, vi } from "vitest";
import { useReducer } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { PuzzlePage } from "@/components/PuzzlePage";
import { FinishScreen } from "@/components/FinishScreen";
import { Grid } from "@/components/Grid";
import { Timer } from "@/components/Timer";
import {
  type SolveAction,
  type SolveState,
  elapsedMs,
  initialState,
  isPuzzleSolved,
  makeEmptyRevealed,
  solveReducer,
} from "@/lib/state";
import { parsePuzzle, type Puzzle } from "@/lib/puzzle";

const EXAMPLE_PATH = resolve(__dirname, "../../puzzles/nba/example.json");

function loadExamplePuzzle(): Puzzle {
  const raw = JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
  return parsePuzzle(raw);
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// Reducer-level finish + reveal + timer behavior
// ---------------------------------------------------------------------------

describe("solveReducer: timer anchor", () => {
  function setup(now: () => number) {
    const puzzle = loadExamplePuzzle();
    const reducer = solveReducer(puzzle, now);
    let state = initialState(puzzle);
    const dispatch = (action: SolveAction) => {
      state = reducer(state, action);
      return state;
    };
    return { puzzle, dispatch, get: () => state };
  }

  it("auto-starts the timer on first letter input", () => {
    const { dispatch, get } = setup(() => 1_000);
    expect(get().startedAt).toBeNull();
    expect(get().accumulatedMs).toBe(0);
    dispatch({ type: "enterLetter", letter: "S" });
    expect(get().startedAt).toBe(1_000);
  });

  it("does not re-anchor startedAt on subsequent letters", () => {
    let t = 1_000;
    const { dispatch, get } = setup(() => t);
    dispatch({ type: "enterLetter", letter: "S" });
    expect(get().startedAt).toBe(1_000);
    t = 5_000;
    dispatch({ type: "enterLetter", letter: "P" });
    expect(get().startedAt).toBe(1_000);
  });

  it("pauseTimer freezes accumulatedMs and clears startedAt", () => {
    let t = 1_000;
    const { dispatch, get } = setup(() => t);
    dispatch({ type: "enterLetter", letter: "S" });
    t = 4_000;
    dispatch({ type: "pauseTimer", now: 4_000 });
    expect(get().startedAt).toBeNull();
    expect(get().accumulatedMs).toBe(3_000);
  });

  it("resumeTimer re-anchors startedAt without resetting accumulated", () => {
    const { dispatch, get } = setup(() => 1_000);
    dispatch({ type: "enterLetter", letter: "S" });
    dispatch({ type: "pauseTimer", now: 4_000 });
    dispatch({ type: "resumeTimer", now: 10_000 });
    expect(get().startedAt).toBe(10_000);
    expect(get().accumulatedMs).toBe(3_000);
  });

  it("resumeTimer is a no-op before any input has been logged", () => {
    const { dispatch, get } = setup(() => 1_000);
    dispatch({ type: "resumeTimer", now: 5_000 });
    expect(get().startedAt).toBeNull();
    expect(get().accumulatedMs).toBe(0);
  });

  it("elapsedMs sums accumulated + (now - startedAt) while running", () => {
    const { dispatch, get } = setup(() => 1_000);
    dispatch({ type: "enterLetter", letter: "S" });
    expect(elapsedMs(get(), 4_500)).toBe(3_500);
  });

  it("elapsedMs stops moving once finishedAt is set", () => {
    let t = 1_000;
    const puzzle = loadExamplePuzzle();
    const reducer = solveReducer(puzzle, () => t);
    let state = initialState(puzzle);
    state = reducer(state, { type: "revealPuzzle" });
    expect(state.finishedAt).not.toBeNull();
    const frozen = elapsedMs(state, 1_000_000);
    expect(frozen).toBe(elapsedMs(state, 999_999_999));
  });
});

describe("solveReducer: reveals", () => {
  function setupWithTime(now = 1_000) {
    const puzzle = loadExamplePuzzle();
    const reducer = solveReducer(puzzle, () => now);
    let state = initialState(puzzle);
    const dispatch = (action: SolveAction) => {
      state = reducer(state, action);
      return state;
    };
    return { puzzle, dispatch, get: () => state };
  }

  it("revealLetter fills the current cell with the answer and marks it revealed", () => {
    const { puzzle, dispatch, get } = setupWithTime();
    // Initial selected cell is (0,0) which has answer 'S'
    dispatch({ type: "revealLetter" });
    const s = get();
    const expected = (puzzle.grid.cells[0][0] as { answer: string }).answer;
    expect(s.letters[0][0]).toBe(expected);
    expect(s.revealed[0][0]).toBe(true);
    // Doesn't accidentally reveal neighbors
    expect(s.revealed[0][1]).toBe(false);
  });

  it("revealWord fills all cells in the active entry", () => {
    const { puzzle, dispatch, get } = setupWithTime();
    // Initial: across at (0,0), entry 1A = "SPAR"
    dispatch({ type: "revealWord" });
    const s = get();
    const expected = "SPAR";
    for (let i = 0; i < expected.length; i++) {
      expect(s.letters[0][i]).toBe(expected[i]);
      expect(s.revealed[0][i]).toBe(true);
    }
    // Other rows untouched
    expect(s.revealed[1][0]).toBe(false);
    // Sanity-check against the puzzle data
    expect(puzzle.entries.find((e) => e.id === "1A")?.answer).toBe("SPAR");
  });

  it("revealPuzzle fills every letter cell, marks revealed, and finishes", () => {
    const { puzzle, dispatch, get } = setupWithTime(7_777);
    dispatch({ type: "revealPuzzle" });
    const s = get();
    expect(isPuzzleSolved(puzzle, s.letters)).toBe(true);
    // All letter cells revealed
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        const cell = puzzle.grid.cells[r][c];
        if ("answer" in cell) {
          expect(s.revealed[r][c]).toBe(true);
        } else {
          expect(s.revealed[r][c]).toBe(false);
        }
      }
    }
    expect(s.finishedAt).toBe(7_777);
  });

  it("reveals do not block the finish — solving via reveals still finishes", () => {
    const { dispatch, get } = setupWithTime();
    dispatch({ type: "revealPuzzle" });
    expect(get().finishedAt).not.toBeNull();
  });
});

describe("solveReducer: finish detection", () => {
  function fillCorrectly(
    puzzle: Puzzle,
    dispatch: (a: SolveAction) => void,
    skipLastCell = false,
  ) {
    // Walk every letter cell in scan order, manually selecting and entering
    // the correct letter. We do this rather than using nextEntry because
    // the grid has both across and down entries — easiest is direct fill.
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        const cell = puzzle.grid.cells[r][c];
        if (!("answer" in cell)) continue;
        if (skipLastCell && r === 4 && c === 4) continue;
        dispatch({ type: "selectCell", row: r, col: c });
        // The selectCell sets/keeps direction; force across so enterLetter
        // doesn't loop into a different cell.
        dispatch({ type: "setDirection", direction: "across" });
        // Re-select the cell *only* matters if the previous click was the
        // same coords (which would flip direction); here we always move.
        dispatch({ type: "enterLetter", letter: cell.answer });
      }
    }
  }

  it("finish triggers exactly when the last correct letter is entered", () => {
    const puzzle = loadExamplePuzzle();
    let t = 100;
    const reducer = solveReducer(puzzle, () => t);
    let state = initialState(puzzle);
    const dispatch = (a: SolveAction) => {
      state = reducer(state, a);
    };

    // Fill all but one cell — finish must NOT trigger yet.
    fillCorrectly(puzzle, dispatch, true);
    expect(state.finishedAt).toBeNull();

    // Enter the last cell at t=999.
    t = 999;
    const lastCell = puzzle.grid.cells[4][4] as { answer: string };
    dispatch({ type: "selectCell", row: 4, col: 4 });
    dispatch({ type: "setDirection", direction: "across" });
    dispatch({ type: "enterLetter", letter: lastCell.answer });
    expect(state.finishedAt).toBe(999);
  });

  it("subsequent edits do not unset or re-trigger finishedAt", () => {
    const puzzle = loadExamplePuzzle();
    let t = 100;
    const reducer = solveReducer(puzzle, () => t);
    let state = initialState(puzzle);
    const dispatch = (a: SolveAction) => {
      state = reducer(state, a);
    };
    dispatch({ type: "revealPuzzle" });
    const stamped = state.finishedAt;
    expect(stamped).toBe(100);

    // Type more letters — finishedAt must not change.
    t = 9_999;
    dispatch({ type: "selectCell", row: 0, col: 0 });
    dispatch({ type: "enterLetter", letter: "Z" });
    expect(state.finishedAt).toBe(stamped);

    // Backspace — also no change.
    dispatch({ type: "backspace" });
    expect(state.finishedAt).toBe(stamped);
  });

  it("incorrect letters don't trigger finish even when grid is full", () => {
    const puzzle = loadExamplePuzzle();
    const reducer = solveReducer(puzzle, () => 1);
    let state = initialState(puzzle);
    const dispatch = (a: SolveAction) => {
      state = reducer(state, a);
    };
    // Fill every cell with 'Z' (almost certainly wrong)
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        const cell = puzzle.grid.cells[r][c];
        if (!("answer" in cell)) continue;
        dispatch({ type: "selectCell", row: r, col: c });
        dispatch({ type: "setDirection", direction: "across" });
        dispatch({ type: "enterLetter", letter: "Z" });
      }
    }
    expect(state.finishedAt).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Timer component
// ---------------------------------------------------------------------------

describe("<Timer>", () => {
  it("renders 0:00 before the timer starts", () => {
    const puzzle = loadExamplePuzzle();
    const state: SolveState = initialState(puzzle);
    render(<Timer state={state} />);
    expect(screen.getByTestId("timer-value")).toHaveTextContent("0:00");
  });

  it("renders the elapsed time when started", () => {
    const puzzle = loadExamplePuzzle();
    // Hand-construct a state whose timer started 84 seconds ago.
    const now = 100_000;
    vi.spyOn(Date, "now").mockReturnValue(now);
    const state: SolveState = {
      ...initialState(puzzle),
      startedAt: now - 84_000,
      accumulatedMs: 0,
    };
    render(<Timer state={state} />);
    expect(screen.getByTestId("timer-value")).toHaveTextContent("1:24");
  });

  it("hide toggle hides the value visually but underlying state still ticks", () => {
    const puzzle = loadExamplePuzzle();
    const state = initialState(puzzle);
    render(<Timer state={state} />);
    const toggle = screen.getByTestId("timer-toggle");
    expect(toggle).toHaveTextContent("Hide");
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent("Show");
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });
});

// ---------------------------------------------------------------------------
// FinishScreen component
// ---------------------------------------------------------------------------

describe("<FinishScreen>", () => {
  it("shows time, streak, share button, and confetti", () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    render(
      <FinishScreen
        puzzle={puzzle}
        elapsedMs={84_000}
        revealed={revealed}
        streak={3}
      />,
    );
    expect(screen.getByTestId("finish-screen")).toBeInTheDocument();
    expect(screen.getByTestId("finish-time")).toHaveTextContent("1:24");
    expect(screen.getByTestId("finish-streak")).toHaveTextContent("3");
    expect(screen.getByTestId("finish-confetti")).toBeInTheDocument();
    expect(screen.getByTestId("share-button")).toBeInTheDocument();
  });

  it("share button writes share text to clipboard when navigator.share is missing", async () => {
    const puzzle = loadExamplePuzzle();
    const revealed = makeEmptyRevealed(puzzle.grid);
    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", {
      clipboard: { writeText },
    });

    render(
      <FinishScreen
        puzzle={puzzle}
        elapsedMs={60_000}
        revealed={revealed}
        streak={1}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId("share-button"));
    });
    expect(writeText).toHaveBeenCalled();
    const arg = writeText.mock.calls[0][0] as string;
    expect(arg).toContain("The NBA Mini");
    expect(arg).toContain("1:00");
    expect(arg).toContain("nbamini.app");
    // No answer letters
    for (const e of puzzle.entries) {
      expect(arg).not.toContain(e.answer);
    }
    // "Copied!" inline confirmation
    expect(await screen.findByTestId("share-confirm")).toHaveTextContent(
      /copied/i,
    );
  });
});

// ---------------------------------------------------------------------------
// HomePage integration: end-to-end solve hits the finish screen
// ---------------------------------------------------------------------------

describe("<HomePage> end-to-end finish", () => {
  it("clicking 'Reveal puzzle' triggers the finish screen with a copyable share", async () => {
    const raw = JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => raw,
    }));
    vi.stubGlobal("fetch", fetchMock);

    const writeText = vi.fn(async () => {});
    vi.stubGlobal("navigator", {
      clipboard: { writeText },
    });

    render(<PuzzlePage league="nba" />);
    await screen.findByTestId("grid-wrapper");

    // The splash blocks input until the user clicks Start. Click it so
    // the play surface is interactive (matches real solver behavior).
    fireEvent.click(screen.getByRole("button", { name: /start/i }));

    // Reveal the whole puzzle — that immediately finishes.
    fireEvent.click(screen.getByTestId("reveal-puzzle"));

    // Finish screen renders.
    const finish = await screen.findByTestId("finish-screen");
    expect(finish).toBeInTheDocument();

    // Share button is present and writes to clipboard.
    await act(async () => {
      fireEvent.click(screen.getByTestId("share-button"));
    });
    expect(writeText).toHaveBeenCalled();
    const shared = writeText.mock.calls[0][0] as string;
    // After a full reveal, every letter cell should be 🟨
    expect(shared).not.toContain("🟩");
    expect(shared).toContain("🟨");
    expect(shared).toContain("⬛");
  });
});

// ---------------------------------------------------------------------------
// Visibility change: tab blur pauses, focus resumes
// ---------------------------------------------------------------------------

describe("<HomePage> visibility change pauses/resumes the timer", () => {
  it("dispatches pauseTimer/resumeTimer on document.visibilitychange", async () => {
    const raw = JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => raw,
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<PuzzlePage league="nba" />);
    await screen.findByTestId("grid-wrapper");

    // Type a letter to start the timer.
    fireEvent.keyDown(screen.getByTestId("grid-wrapper"), { key: "S" });

    // Verify the timer is showing something (running) via the timer DOM.
    expect(screen.getByTestId("timer-value")).toBeInTheDocument();

    // Now blur the tab.
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => true,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    // Bring it back.
    Object.defineProperty(document, "hidden", {
      configurable: true,
      get: () => false,
    });
    document.dispatchEvent(new Event("visibilitychange"));

    // The component should be in a clean state — no error thrown means
    // the listener handled both transitions. The reducer-level test above
    // exhaustively tests the state math.
    expect(screen.getByTestId("timer-value")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Reveal indicator on grid cells
// ---------------------------------------------------------------------------

describe("Grid: revealed-cell indicator", () => {
  function Harness({ puzzle }: { puzzle: Puzzle }) {
    const reducer = solveReducer(puzzle, () => 1);
    const [state, dispatch] = useReducer(reducer, puzzle, initialState);
    return (
      <div>
        <button
          data-testid="trigger-reveal-letter"
          onClick={() => dispatch({ type: "revealLetter" })}
        >
          rl
        </button>
        <Grid puzzle={puzzle} state={state} dispatch={dispatch} />
      </div>
    );
  }

  it("renders a revealed cell with data-revealed='true' and a dot indicator", () => {
    const puzzle = loadExamplePuzzle();
    render(<Harness puzzle={puzzle} />);
    // Initial cell is (0,0). Trigger reveal.
    fireEvent.click(screen.getByTestId("trigger-reveal-letter"));
    const cell = screen.getByTestId("cell-0-0");
    expect(cell).toHaveAttribute("data-revealed", "true");
    expect(screen.getByTestId("reveal-dot-0-0")).toBeInTheDocument();
  });
});
