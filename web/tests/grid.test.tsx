import { afterEach, describe, expect, it, vi } from "vitest";
import { useReducer } from "react";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import HomePage from "@/app/page";
import { Grid } from "@/components/Grid";
import { ClueBar } from "@/components/ClueBar";
import {
  computeEntryNumbers,
  findActiveEntry,
  initialState,
  solveReducer,
  sortedEntriesForNav,
} from "@/lib/state";
import { parsePuzzle, type Puzzle } from "@/lib/puzzle";

const EXAMPLE_PATH = resolve(__dirname, "../../puzzles/example.json");

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
// Pure-state tests (reducer + selectors). These exercise the brains of the
// component without rendering anything.
// ---------------------------------------------------------------------------

describe("computeEntryNumbers (example puzzle)", () => {
  it("assigns the expected numbers in scan order", () => {
    const puzzle = loadExamplePuzzle();
    const entryNumbers = computeEntryNumbers(puzzle.grid);
    // Verify: 9 numbered cells in the example, numbers are 1..9 in scan order.
    expect(entryNumbers.map((e) => e.number)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
    // (0,0) starts BOTH across and down, so it shares number 1 between 1A and 1D.
    const first = entryNumbers[0];
    expect(first).toMatchObject({ row: 0, col: 0, number: 1 });
    expect(first.startsAcross).toBe(true);
    expect(first.startsDown).toBe(true);
    // (1,0) is 5: only across (above is a letter, so no down start).
    const five = entryNumbers.find((e) => e.number === 5);
    expect(five).toMatchObject({ row: 1, col: 0, startsAcross: true, startsDown: false });
  });
});

describe("solveReducer (example puzzle)", () => {
  function setup() {
    const puzzle = loadExamplePuzzle();
    const reducer = solveReducer(puzzle);
    let state = initialState(puzzle);
    const dispatch = (action: Parameters<typeof reducer>[1]) => {
      state = reducer(state, action);
      return state;
    };
    return { puzzle, dispatch, get: () => state };
  }

  it("starts with the first letter cell selected and across direction", () => {
    const { get } = setup();
    expect(get().selectedCell).toEqual({ row: 0, col: 0 });
    expect(get().direction).toBe("across");
  });

  it("typing a letter writes it and advances the cursor", () => {
    const { dispatch, get } = setup();
    dispatch({ type: "enterLetter", letter: "s" });
    const s = get();
    expect(s.letters[0][0]).toBe("S");
    expect(s.selectedCell).toEqual({ row: 0, col: 1 });
  });

  it("backspace on an empty cell retreats and clears the previous", () => {
    const { dispatch, get } = setup();
    dispatch({ type: "enterLetter", letter: "S" });
    dispatch({ type: "enterLetter", letter: "P" });
    // cursor now at (0,2). Backspace into empty (0,2) should retreat to (0,1) and clear it.
    dispatch({ type: "backspace" });
    expect(get().selectedCell).toEqual({ row: 0, col: 1 });
    expect(get().letters[0][1]).toBeNull();
  });

  it("backspace on a filled cell clears it without moving", () => {
    const { dispatch, get } = setup();
    dispatch({ type: "enterLetter", letter: "S" }); // (0,0)=S, cursor at (0,1)
    // manually overwrite cursor: select (0,0) again
    dispatch({ type: "selectCell", row: 0, col: 0 });
    // Now (0,0) is selected and has 'S'. Backspace clears it but stays put.
    dispatch({ type: "backspace" });
    expect(get().letters[0][0]).toBeNull();
    expect(get().selectedCell).toEqual({ row: 0, col: 0 });
  });

  it("clicking a black square is a no-op", () => {
    const { dispatch, get } = setup();
    const before = get().selectedCell;
    dispatch({ type: "selectCell", row: 0, col: 4 }); // (0,4) is a block
    expect(get().selectedCell).toEqual(before);
  });

  it("clicking the currently selected cell flips direction", () => {
    const { dispatch, get } = setup();
    expect(get().direction).toBe("across");
    dispatch({ type: "selectCell", row: 0, col: 0 });
    expect(get().direction).toBe("down");
    dispatch({ type: "selectCell", row: 0, col: 0 });
    expect(get().direction).toBe("across");
  });

  it("perpendicular arrow flips direction without moving", () => {
    const { dispatch, get } = setup();
    // Across mode at (0,0). Pressing Down should flip to down, not move.
    dispatch({ type: "arrow", dRow: 1, dCol: 0 });
    expect(get().direction).toBe("down");
    expect(get().selectedCell).toEqual({ row: 0, col: 0 });
  });

  it("arrow movement skips over blocks", () => {
    const { dispatch, get } = setup();
    // Move to (0,3) — (0,4) is a block, ArrowRight should jump to nothing.
    dispatch({ type: "selectCell", row: 0, col: 3 });
    dispatch({ type: "arrow", dRow: 0, dCol: 1 });
    // No letter cell beyond a block in row 0 → cursor doesn't move.
    expect(get().selectedCell).toEqual({ row: 0, col: 3 });

    // From (4,1), pressing ArrowLeft: (4,0) is a block → no further letter
    // exists to the left → cursor stays.
    dispatch({ type: "selectCell", row: 4, col: 1 });
    // selectCell sets direction back to across only if same cell; but we're
    // also currently in down direction — switch to across explicitly.
    dispatch({ type: "setDirection", direction: "across" });
    dispatch({ type: "arrow", dRow: 0, dCol: -1 });
    expect(get().selectedCell).toEqual({ row: 4, col: 1 });
  });

  it("Tab cycles to the next entry", () => {
    const { puzzle, dispatch, get } = setup();
    // Starting state: (0,0) across → entry 1A.
    const sorted = sortedEntriesForNav(puzzle);
    const firstActive = findActiveEntry(puzzle, 0, 0, "across");
    expect(firstActive?.id).toBe("1A");
    expect(sorted[0].id).toBe("1A");

    dispatch({ type: "nextEntry" });
    const after = get();
    const nextEntry = findActiveEntry(
      puzzle,
      after.selectedCell!.row,
      after.selectedCell!.col,
      after.direction,
    );
    expect(nextEntry?.id).toBe(sorted[1].id);
  });

  it("Shift-Tab wraps to the previous entry", () => {
    const { puzzle, dispatch, get } = setup();
    const sorted = sortedEntriesForNav(puzzle);
    dispatch({ type: "previousEntry" });
    const after = get();
    const e = findActiveEntry(
      puzzle,
      after.selectedCell!.row,
      after.selectedCell!.col,
      after.direction,
    );
    expect(e?.id).toBe(sorted[sorted.length - 1].id);
  });

  it("typing past the end of a run leaves the cursor on the last cell", () => {
    const { dispatch, get } = setup();
    // 1A is "SPAR" (length 4). Type S P A R — cursor should end up still at
    // (0,3) since (0,4) is a block.
    dispatch({ type: "enterLetter", letter: "S" });
    dispatch({ type: "enterLetter", letter: "P" });
    dispatch({ type: "enterLetter", letter: "A" });
    dispatch({ type: "enterLetter", letter: "R" });
    expect(get().selectedCell).toEqual({ row: 0, col: 3 });
    expect(get().letters[0]).toEqual(["S", "P", "A", "R", null]);
  });
});

// ---------------------------------------------------------------------------
// Component-rendering tests
// ---------------------------------------------------------------------------

describe("<Grid> rendering", () => {
  function renderGridFor(puzzle: Puzzle) {
    function Harness() {
      const reducer = solveReducer(puzzle);
      const [state, dispatch] = useReducer(reducer, puzzle, initialState);
      return <Grid puzzle={puzzle} state={state} dispatch={dispatch} />;
    }
    return render(<Harness />);
  }

  it("renders 5x5 cells with the right black squares and entry numbers", () => {
    const puzzle = loadExamplePuzzle();
    renderGridFor(puzzle);

    // 25 grid cells total
    for (let r = 0; r < 5; r++) {
      for (let c = 0; c < 5; c++) {
        expect(screen.getByTestId(`cell-${r}-${c}`)).toBeInTheDocument();
      }
    }
    // Black squares per the example fixture: (0,4) and (4,0)
    expect(screen.getByTestId("cell-0-4")).toHaveAttribute("data-block", "true");
    expect(screen.getByTestId("cell-4-0")).toHaveAttribute("data-block", "true");
    // Numbers 1, 5, 7, 8, 9 should appear as text inside the grid.
    expect(screen.getByTestId("cell-0-0")).toHaveTextContent("1");
    expect(screen.getByTestId("cell-1-0")).toHaveTextContent("5");
    expect(screen.getByTestId("cell-2-0")).toHaveTextContent("7");
    expect(screen.getByTestId("cell-3-0")).toHaveTextContent("8");
    expect(screen.getByTestId("cell-4-1")).toHaveTextContent("9");
  });

  it("typing a letter into the grid renders the letter in the cell", () => {
    const puzzle = loadExamplePuzzle();
    renderGridFor(puzzle);
    const wrapper = screen.getByTestId("grid-wrapper");
    fireEvent.keyDown(wrapper, { key: "S" });
    expect(screen.getByTestId("letter-0-0")).toHaveTextContent("S");
  });

  it("clicking a black cell does not select it", () => {
    const puzzle = loadExamplePuzzle();
    renderGridFor(puzzle);
    const block = screen.getByTestId("cell-0-4");
    // Block cells don't have an onClick handler attached, but firing one
    // shouldn't change selection either way. The first cell stays selected.
    fireEvent.click(block);
    expect(screen.getByTestId("cell-0-0")).toHaveAttribute(
      "data-selected",
      "true",
    );
  });

  it("clicking the currently selected cell flips the active run highlight", () => {
    const puzzle = loadExamplePuzzle();
    renderGridFor(puzzle);
    // Initial: across at (0,0) — row 0 cells (0,0)..(0,3) highlighted (active run).
    expect(screen.getByTestId("cell-0-1")).toHaveAttribute(
      "data-active-run",
      "true",
    );
    expect(screen.getByTestId("cell-1-0")).not.toHaveAttribute("data-active-run");

    fireEvent.click(screen.getByTestId("cell-0-0"));
    // After flip: down at (0,0) — column 0 cells (0,0)..(3,0) highlighted.
    expect(screen.getByTestId("cell-1-0")).toHaveAttribute(
      "data-active-run",
      "true",
    );
    expect(screen.getByTestId("cell-0-1")).not.toHaveAttribute("data-active-run");
  });
});

// ---------------------------------------------------------------------------
// ClueBar
// ---------------------------------------------------------------------------

describe("<ClueBar>", () => {
  it("shows the active entry's number, direction, and clue", () => {
    const puzzle = loadExamplePuzzle();
    const entry = puzzle.entries.find((e) => e.id === "5A")!;
    render(<ClueBar puzzle={puzzle} activeEntry={entry} />);
    const tag = screen.getByTestId("clue-tag");
    expect(tag).toHaveTextContent(/5A/);
    expect(screen.getByTestId("clue-text")).toHaveTextContent(/ACROSS/);
    expect(screen.getByTestId("clue-text")).toHaveTextContent(entry.clue);
  });

  it("renders a placeholder when no entry is active", () => {
    const puzzle = loadExamplePuzzle();
    render(<ClueBar puzzle={puzzle} activeEntry={null} />);
    expect(screen.getByRole("region", { name: /active clue/i })).toHaveTextContent(
      /select a cell/i,
    );
  });
});

// ---------------------------------------------------------------------------
// HomePage integration: fetch flow
// ---------------------------------------------------------------------------

describe("<HomePage> (integration)", () => {
  it("renders the dormant state when the fetch returns 404", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({}),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<HomePage />);
    const dormant = await screen.findByTestId("no-puzzle");
    expect(dormant).toHaveTextContent(/no NBA games yesterday/i);
  });

  it("renders the grid when the fetch returns the example puzzle", async () => {
    const raw = JSON.parse(readFileSync(EXAMPLE_PATH, "utf-8"));
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => raw,
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<HomePage />);
    await screen.findByTestId("grid-wrapper");
    expect(screen.getByTestId("cell-0-0")).toBeInTheDocument();
    expect(screen.getByTestId("cell-0-4")).toHaveAttribute("data-block", "true");
    // ClueBar should be showing 1A initially
    expect(screen.getByTestId("clue-tag")).toHaveTextContent(/1A/);
  });
});
