"use client";

import { useEffect, useMemo, useReducer, useState } from "react";

import { ClueBar } from "@/components/ClueBar";
import { FinishScreen } from "@/components/FinishScreen";
import { Grid } from "@/components/Grid";
import { Timer } from "@/components/Timer";
import { fetchTodayPuzzle, type Puzzle } from "@/lib/puzzle";
import {
  elapsedMs,
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
      <header
        style={{
          marginBottom: 24,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <h1
          style={{
            fontFamily: '"Iowan Old Style", "Charter", "Georgia", serif',
            fontSize: 28,
            margin: 0,
          }}
        >
          The NBA Mini
        </h1>
        {/* U12 will land <StreakBadge /> here. */}
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

  // Pause/resume the timer on tab visibility transitions. Browsers throttle
  // setInterval in background tabs anyway, but anchoring the elapsed time
  // to wall-clock means a long backgrounded tab would otherwise charge the
  // user for time they spent elsewhere. Pause keeps "your solve time" honest.
  useEffect(() => {
    if (typeof document === "undefined") return;
    function onVisibility() {
      if (document.hidden) {
        dispatch({ type: "pauseTimer", now: Date.now() });
      } else {
        dispatch({ type: "resumeTimer", now: Date.now() });
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const isFinished = state.finishedAt !== null;
  // Snapshot the elapsed at finish so the FinishScreen doesn't tick.
  const finalElapsed = useMemo(
    () => (isFinished ? elapsedMs(state, Date.now()) : 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isFinished, state.finishedAt],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
        }}
      >
        <Timer state={state} />
        <RevealMenu
          onRevealLetter={() => dispatch({ type: "revealLetter" })}
          onRevealWord={() => dispatch({ type: "revealWord" })}
          onRevealPuzzle={() => dispatch({ type: "revealPuzzle" })}
        />
      </div>
      <Grid puzzle={puzzle} state={state} dispatch={dispatch} />
      <ClueBar puzzle={puzzle} activeEntry={activeEntry} />

      {isFinished && (
        <FinishScreen
          puzzle={puzzle}
          elapsedMs={finalElapsed}
          revealed={state.revealed}
          // v0 hardcodes streak=1; U12 wires the real localStorage value.
          streak={1}
        />
      )}
    </div>
  );
}

/**
 * Three-button reveal menu. Per the plan, simple buttons beat a dropdown
 * for testability and accessibility. We don't bother hiding the buttons
 * behind a parent toggle — they're small and unobtrusive.
 */
function RevealMenu({
  onRevealLetter,
  onRevealWord,
  onRevealPuzzle,
}: {
  onRevealLetter: () => void;
  onRevealWord: () => void;
  onRevealPuzzle: () => void;
}) {
  return (
    <div
      data-testid="reveal-menu"
      style={{ display: "flex", gap: 6, fontSize: 12 }}
    >
      <button
        type="button"
        data-testid="reveal-letter"
        onClick={onRevealLetter}
        style={revealButtonStyle}
      >
        Reveal letter
      </button>
      <button
        type="button"
        data-testid="reveal-word"
        onClick={onRevealWord}
        style={revealButtonStyle}
      >
        Reveal word
      </button>
      <button
        type="button"
        data-testid="reveal-puzzle"
        onClick={onRevealPuzzle}
        style={revealButtonStyle}
      >
        Reveal puzzle
      </button>
    </div>
  );
}

const revealButtonStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #c4c1b6",
  borderRadius: 4,
  padding: "4px 8px",
  fontSize: 12,
  color: "#333",
  cursor: "pointer",
};
