"use client";

import { useEffect, useMemo, useReducer, useState } from "react";

import { ClueBar } from "@/components/ClueBar";
import { Grid } from "@/components/Grid";
import { fetchTodayPuzzle, type Puzzle } from "@/lib/puzzle";
import {
  findActiveEntry,
  initialState,
  solveReducer,
} from "@/lib/state";

type FetchStatus =
  | { kind: "loading" }
  | { kind: "ready"; puzzle: Puzzle }
  | { kind: "no-puzzle" }
  | { kind: "error"; message: string };

export default function HomePage() {
  const [status, setStatus] = useState<FetchStatus>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchTodayPuzzle()
      .then((puzzle) => {
        if (cancelled) return;
        if (puzzle) setStatus({ kind: "ready", puzzle });
        else setStatus({ kind: "no-puzzle" });
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setStatus({
          kind: "error",
          message: err instanceof Error ? err.message : String(err),
        });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main
      style={{
        padding: 24,
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        maxWidth: 720,
        margin: "0 auto",
      }}
    >
      <header style={{ marginBottom: 24 }}>
        <h1
          style={{
            fontFamily: '"Iowan Old Style", "Charter", "Georgia", serif',
            fontSize: 28,
            margin: 0,
          }}
        >
          The NBA Mini
        </h1>
      </header>

      {status.kind === "loading" && <p>Loading today&rsquo;s puzzle&hellip;</p>}

      {status.kind === "no-puzzle" && (
        <div
          role="status"
          data-testid="no-puzzle"
          style={{
            padding: 24,
            background: "#f1efe8",
            borderRadius: 8,
            color: "#333",
          }}
        >
          <h2 style={{ marginTop: 0 }}>No puzzle today</h2>
          <p style={{ margin: 0 }}>
            There were no NBA games yesterday. Streaks pause on off-days &mdash;
            see you tomorrow.
          </p>
        </div>
      )}

      {status.kind === "error" && (
        <div role="alert" style={{ color: "#a00" }}>
          Couldn&rsquo;t load today&rsquo;s puzzle: {status.message}
        </div>
      )}

      {status.kind === "ready" && <PuzzleView puzzle={status.puzzle} />}
    </main>
  );
}

function PuzzleView({ puzzle }: { puzzle: Puzzle }) {
  const reducer = useMemo(() => solveReducer(puzzle), [puzzle]);
  const [state, dispatch] = useReducer(reducer, puzzle, initialState);

  const activeEntry = useMemo(() => {
    if (!state.selectedCell) return null;
    return findActiveEntry(
      puzzle,
      state.selectedCell.row,
      state.selectedCell.col,
      state.direction,
    );
  }, [puzzle, state.selectedCell, state.direction]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <Grid puzzle={puzzle} state={state} dispatch={dispatch} />
      <ClueBar puzzle={puzzle} activeEntry={activeEntry} />
    </div>
  );
}
