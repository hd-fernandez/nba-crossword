"use client";

import { useEffect, useMemo, useReducer, useState } from "react";

import { ClueBar } from "@/components/ClueBar";
import { FinishScreen } from "@/components/FinishScreen";
import { Grid } from "@/components/Grid";
import { StreakBadge } from "@/components/StreakBadge";
import { Timer } from "@/components/Timer";
import { fetchTodayPuzzle, todayInEastern, type Puzzle } from "@/lib/puzzle";
import {
  elapsedMs,
  findActiveEntry,
  initialState,
  solveReducer,
} from "@/lib/state";
import { getDisplayStreak, getStreak, markOffDay } from "@/lib/storage";

type FetchStatus =
  | { kind: "loading" }
  | { kind: "ready"; puzzle: Puzzle }
  | { kind: "no-puzzle" }
  | { kind: "error"; message: string };

export default function HomePage() {
  const [status, setStatus] = useState<FetchStatus>({ kind: "loading" });
  // `today` is computed lazily but only on the client (we set it from a
  // mount-time effect). `streak` likewise starts at 0 and gets a real value
  // after mount. Both deferred so SSR + client first-paint match (no
  // hydration mismatch from reading localStorage on the client only).
  const [today, setToday] = useState<string | null>(null);
  const [streak, setStreak] = useState<number>(0);

  useEffect(() => {
    const t = todayInEastern();
    setToday(t);
    // Display streak counts the prior run *up to* today — so a returning
    // user with a 5-day streak sees "🔥 5" on load, even though they
    // haven't completed today yet.
    setStreak(getDisplayStreak(t));
  }, []);

  useEffect(() => {
    if (!today) return;
    let cancelled = false;
    fetchTodayPuzzle()
      .then((puzzle) => {
        if (cancelled) return;
        if (puzzle) {
          setStatus({ kind: "ready", puzzle });
        } else {
          // No puzzle today — record this as an off-day so it doesn't break
          // the streak when the user returns. Idempotent: marking the same
          // date twice is a no-op.
          markOffDay(today);
          setStreak(getDisplayStreak(today));
          setStatus({ kind: "no-puzzle" });
        }
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
  }, [today]);

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
        <StreakBadge streak={streak} />
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

      {status.kind === "ready" && (
        <PuzzleView
          puzzle={status.puzzle}
          onCompletion={() => {
            // `today` will always be set here — `status` only flips to
            // "ready" inside the fetch effect, which only runs after `today`
            // is set. But guard anyway so a future refactor can't NPE.
            if (today) setStreak(getStreak(today));
          }}
        />
      )}
    </main>
  );
}

function PuzzleView({
  puzzle,
  onCompletion,
}: {
  puzzle: Puzzle;
  /**
   * Fired exactly once when this puzzle transitions to finished. The
   * <FinishScreen> is responsible for the actual `recordCompletion()` call;
   * this callback only nudges the parent to re-read its derived state
   * (e.g., the header streak badge).
   */
  onCompletion?: () => void;
}) {
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

  // Fire `onCompletion` exactly once when the puzzle transitions to
  // finished. We don't fire it again on remount — the deps are the
  // `finishedAt` stamp, which is set once and never reset.
  useEffect(() => {
    if (!isFinished) return;
    onCompletion?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFinished, state.finishedAt]);

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
        // No `streak` prop — FinishScreen calls `recordCompletion(puzzle.date)`
        // and computes the streak from localStorage on mount.
        <FinishScreen
          puzzle={puzzle}
          elapsedMs={finalElapsed}
          revealed={state.revealed}
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
