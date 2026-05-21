"use client";

import type { FormEvent, KeyboardEvent, Ref } from "react";
import { forwardRef, useImperativeHandle, useMemo, useRef } from "react";
import type { Puzzle } from "@/lib/puzzle";
import {
  type SolveAction,
  type SolveState,
  entryNumberMap,
  findEntryStart,
  isLetter,
} from "@/lib/state";

interface GridProps {
  puzzle: Puzzle;
  state: SolveState;
  dispatch: (action: SolveAction) => void;
}

/** Imperative handle exposed to parents that want to focus the grid
 *  programmatically — e.g., the splash overlay's Start button needs to
 *  shift keyboard focus into the puzzle so the user can start typing
 *  immediately. */
export interface GridHandle {
  focus(): void;
}

const CELL_SIZE = 60; // px

/**
 * The 5x5 puzzle grid with keyboard + touch input.
 *
 * Mobile keyboard strategy: a hidden text input ("trap") is focused whenever
 * the user taps a cell. Letter keys, backspace, and arrows are captured via
 * onKeyDown on a wrapping div (works for desktop) AND on the trap input
 * (works for mobile soft keyboards). The trap also handles `onInput` as a
 * fallback for soft keyboards that don't fire keydown events.
 *
 * State is owned by the parent (the page component) so the ClueBar can
 * subscribe to the same reducer state — see app/page.tsx.
 */
function GridImpl(
  { puzzle, state, dispatch }: GridProps,
  ref: Ref<GridHandle>,
) {
  const numbers = useMemo(() => entryNumberMap(puzzle.grid), [puzzle]);

  // Cells that belong to the active entry (for highlight styling)
  const activeRunKeys = useMemo(() => {
    const keys = new Set<string>();
    if (!state.selectedCell) return keys;
    const start = findEntryStart(
      puzzle.grid,
      state.selectedCell.row,
      state.selectedCell.col,
      state.direction,
    );
    let r = start.row;
    let c = start.col;
    while (r < puzzle.grid.size && c < puzzle.grid.size) {
      const cell = puzzle.grid.cells[r][c];
      if (!isLetter(cell)) break;
      keys.add(`${r},${c}`);
      if (state.direction === "across") c += 1;
      else r += 1;
    }
    return keys;
  }, [puzzle, state.selectedCell, state.direction]);

  const wrapperRef = useRef<HTMLDivElement>(null);
  const trapRef = useRef<HTMLInputElement>(null);

  function focusGrid() {
    // Prefer the trap input on touch devices (raises soft keyboard);
    // otherwise focus the wrapper for desktop keyboard handling.
    const isTouch =
      typeof window !== "undefined" && "ontouchstart" in window;
    if (isTouch) trapRef.current?.focus();
    else wrapperRef.current?.focus();
  }

  useImperativeHandle(ref, () => ({ focus: focusGrid }), []);

  function handleKeyDown(e: KeyboardEvent) {
    // Don't interfere with browser shortcuts (Cmd+R, Ctrl+L, etc.).
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const key = e.key;
    if (/^[a-zA-Z]$/.test(key)) {
      e.preventDefault();
      dispatch({ type: "enterLetter", letter: key });
      return;
    }
    switch (key) {
      case "Backspace":
        e.preventDefault();
        dispatch({ type: "backspace" });
        return;
      case "ArrowLeft":
        e.preventDefault();
        dispatch({ type: "arrow", dRow: 0, dCol: -1 });
        return;
      case "ArrowRight":
        e.preventDefault();
        dispatch({ type: "arrow", dRow: 0, dCol: 1 });
        return;
      case "ArrowUp":
        e.preventDefault();
        dispatch({ type: "arrow", dRow: -1, dCol: 0 });
        return;
      case "ArrowDown":
        e.preventDefault();
        dispatch({ type: "arrow", dRow: 1, dCol: 0 });
        return;
      case " ":
        e.preventDefault();
        dispatch({ type: "toggleDirection" });
        return;
      case "Tab":
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "previousEntry" : "nextEntry" });
        return;
    }
  }

  // Soft-keyboard input handler (mobile). The trap holds at most one
  // character; we read the last char, dispatch, then clear.
  function handleTrapInput(e: FormEvent<HTMLInputElement>) {
    const t = e.currentTarget;
    const value = t.value;
    if (value.length > 0) {
      const ch = value.charAt(value.length - 1);
      if (/^[a-zA-Z]$/.test(ch)) {
        dispatch({ type: "enterLetter", letter: ch });
      }
      t.value = "";
    }
  }

  return (
    <div
      ref={wrapperRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      data-testid="grid-wrapper"
      style={{
        outline: "none",
        position: "relative",
        display: "inline-block",
      }}
    >
      <div
        role="grid"
        aria-label="5 by 5 mini crossword"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${puzzle.grid.size}, ${CELL_SIZE}px)`,
          gap: 1,
          background: "#1a1a1a",
          border: "2px solid #1a1a1a",
          borderRadius: 6,
          overflow: "hidden",
          boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        }}
      >
        {puzzle.grid.cells.map((row, r) =>
          row.map((cell, c) => {
            const key = `${r},${c}`;
            if (!isLetter(cell)) {
              return (
                <div
                  key={key}
                  data-testid={`cell-${r}-${c}`}
                  data-block="true"
                  role="gridcell"
                  aria-label={`block at row ${r + 1} column ${c + 1}`}
                  style={{
                    width: CELL_SIZE,
                    height: CELL_SIZE,
                    background: "#121212",
                  }}
                />
              );
            }
            const isSelected =
              state.selectedCell?.row === r && state.selectedCell?.col === c;
            const isInActiveRun = activeRunKeys.has(key);
            const isRevealed = state.revealed?.[r]?.[c] === true;
            const number = numbers.get(key);
            const letter = state.letters[r][c] ?? "";
            // Reveal styling is layered behind selection/active-run so the
            // user's current focus still reads first. A subtle warm tint
            // plus a small corner dot is enough to differentiate.
            const bg = isSelected
              ? "#ffe066" // active cell — warmer goldenrod
              : isInActiveRun
                ? isRevealed
                  ? "#e0e8ee" // run + revealed: cool gray
                  : "#cfe6ff" // run only: soft blue
                : isRevealed
                  ? "#fff5d6" // revealed at rest: warm cream
                  : "#fefdf9"; // empty: very warm white
            return (
              <div
                key={key}
                role="gridcell"
                aria-selected={isSelected}
                aria-label={`row ${r + 1} column ${c + 1}${number ? `, entry ${number}` : ""}${letter ? `, ${letter}` : ", empty"}${isRevealed ? ", revealed" : ""}`}
                data-testid={`cell-${r}-${c}`}
                data-selected={isSelected ? "true" : undefined}
                data-active-run={isInActiveRun ? "true" : undefined}
                data-revealed={isRevealed ? "true" : undefined}
                onClick={() => {
                  dispatch({ type: "selectCell", row: r, col: c });
                  focusGrid();
                }}
                style={{
                  width: CELL_SIZE,
                  height: CELL_SIZE,
                  background: bg,
                  position: "relative",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontFamily:
                    'var(--font-serif), "Iowan Old Style", "Charter", "Georgia", serif',
                  fontWeight: 600,
                  fontSize: 24,
                  color: "#1a1a1a",
                  cursor: "pointer",
                  userSelect: "none",
                  transition: "background 100ms ease",
                }}
              >
                {number !== undefined && (
                  <span
                    aria-hidden
                    style={{
                      position: "absolute",
                      top: 3,
                      left: 5,
                      fontFamily: "var(--font-sans), system-ui, sans-serif",
                      fontSize: 10,
                      fontWeight: 600,
                      color: "#666",
                      letterSpacing: "0.02em",
                    }}
                  >
                    {number}
                  </span>
                )}
                {isRevealed && (
                  <span
                    aria-hidden
                    data-testid={`reveal-dot-${r}-${c}`}
                    style={{
                      position: "absolute",
                      bottom: 3,
                      right: 4,
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: "#d39a00",
                    }}
                  />
                )}
                <span data-testid={`letter-${r}-${c}`}>{letter}</span>
              </div>
            );
          }),
        )}
      </div>

      {/* Hidden input: lets soft keyboards open on mobile. */}
      <input
        ref={trapRef}
        type="text"
        inputMode="text"
        autoCapitalize="characters"
        autoCorrect="off"
        autoComplete="off"
        spellCheck={false}
        aria-hidden
        tabIndex={-1}
        onInput={handleTrapInput}
        onKeyDown={handleKeyDown}
        style={{
          position: "absolute",
          opacity: 0,
          pointerEvents: "none",
          height: 0,
          width: 0,
          left: -9999,
        }}
      />
    </div>
  );
}

export const Grid = forwardRef<GridHandle, GridProps>(GridImpl);
Grid.displayName = "Grid";
