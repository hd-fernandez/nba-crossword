"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ClueBar } from "@/components/ClueBar";
import { FinishScreen } from "@/components/FinishScreen";
import { Grid, type GridHandle } from "@/components/Grid";
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
    <>
      {/* Fixed photographic backdrop. The image is a CC0 basketball shot
          at web/public/bg/court.jpg; the dark gradient overlay ensures the
          puzzle card and text stay legible. `position: fixed` so the
          image doesn't repeat when the page is taller than the viewport. */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          backgroundImage: "url(/bg/court.jpg)",
          backgroundSize: "cover",
          backgroundPosition: "center",
          zIndex: -2,
        }}
      />
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          background:
            "linear-gradient(180deg, rgba(10,10,12,0.78) 0%, rgba(10,10,12,0.86) 60%, rgba(10,10,12,0.92) 100%)",
          zIndex: -1,
        }}
      />
      <main
        style={{
          minHeight: "100vh",
          padding: "32px 16px 48px",
          fontFamily:
            'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
          color: "#f7f7f5",
        }}
      >
        <div style={{ maxWidth: 520, margin: "0 auto" }}>
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
                fontSize: 32,
                margin: 0,
                letterSpacing: "-0.01em",
                color: "#fffdf6",
                textShadow: "0 1px 2px rgba(0,0,0,0.5)",
              }}
            >
              The NBA Mini
            </h1>
            <StreakBadge streak={streak} />
          </header>

          {status.kind === "loading" && (
            <p style={{ color: "#d9d9d6" }}>Loading today&rsquo;s puzzle&hellip;</p>
          )}

          {status.kind === "no-puzzle" && (
            <div
              role="status"
              data-testid="no-puzzle"
              style={{
                padding: 24,
                background: "rgba(255, 253, 246, 0.96)",
                borderRadius: 12,
                color: "#1a1a1a",
                boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
              }}
            >
              <h2 style={{ marginTop: 0 }}>No puzzle today</h2>
              <p style={{ margin: 0 }}>
                There were no NBA games yesterday. Streaks pause on off-days
                &mdash; see you tomorrow.
              </p>
            </div>
          )}

          {status.kind === "error" && (
            <div
              role="alert"
              style={{
                color: "#fff",
                background: "rgba(160, 0, 0, 0.85)",
                padding: 16,
                borderRadius: 8,
              }}
            >
              Couldn&rsquo;t load today&rsquo;s puzzle: {status.message}
            </div>
          )}

          {status.kind === "ready" && (
            <div
              style={{
                background: "rgba(255, 253, 246, 0.97)",
                borderRadius: 14,
                padding: 20,
                boxShadow: "0 16px 50px rgba(0,0,0,0.4)",
                color: "#1a1a1a",
              }}
            >
              <PuzzleView
                puzzle={status.puzzle}
                onCompletion={() => {
                  // `today` will always be set here — `status` only flips to
                  // "ready" inside the fetch effect, which only runs after
                  // `today` is set. But guard anyway so a future refactor
                  // can't NPE.
                  if (today) setStreak(getStreak(today));
                }}
              />
            </div>
          )}

          <footer
            style={{
              marginTop: 24,
              fontSize: 11,
              color: "rgba(247, 247, 245, 0.55)",
              textAlign: "center",
              letterSpacing: "0.05em",
            }}
          >
            Photo: Unsplash · CC0
          </footer>
        </div>
      </main>
    </>
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
  const [started, setStarted] = useState(false);
  const gridRef = useRef<GridHandle>(null);

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
  // Only attached after the user clicks Start so we don't pause-with-zero a
  // splash that hasn't been started yet.
  useEffect(() => {
    if (!started || typeof document === "undefined") return;
    function onVisibility() {
      if (document.hidden) {
        dispatch({ type: "pauseTimer", now: Date.now() });
      } else {
        dispatch({ type: "resumeTimer", now: Date.now() });
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [started]);

  function handleStart() {
    if (started) return;
    setStarted(true);
    dispatch({ type: "startTimer", now: Date.now() });
    // Focus on the next tick so the Grid is unblurred + interactive when
    // we hand it focus. requestAnimationFrame is a safer "after layout" hook
    // than setTimeout(0) on most browsers.
    requestAnimationFrame(() => gridRef.current?.focus());
  }

  const isFinished = state.finishedAt !== null;
  // The modal can be dismissed; finish state itself is permanent.
  const [finishDismissed, setFinishDismissed] = useState(false);
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
    <div style={{ display: "flex", flexDirection: "column", gap: 16, position: "relative" }}>
      <div
        // Blur the play surface until the user clicks Start. Pointer-events
        // off so a stray click on the blurred clues doesn't focus the grid
        // before the splash is dismissed.
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 16,
          filter: started ? "none" : "blur(6px)",
          transition: "filter 200ms ease-out",
          pointerEvents: started ? "auto" : "none",
          userSelect: started ? "auto" : "none",
        }}
        aria-hidden={!started}
      >
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
        <Grid ref={gridRef} puzzle={puzzle} state={state} dispatch={dispatch} />
        <ClueBar puzzle={puzzle} activeEntry={activeEntry} />
      </div>

      {!started && (
        <SplashOverlay
          puzzleNumber={puzzle.puzzle_number}
          puzzleDate={puzzle.date}
          onStart={handleStart}
        />
      )}

      {started && isFinished && !finishDismissed && (
        // No `streak` prop — FinishScreen calls `recordCompletion(puzzle.date)`
        // and computes the streak from localStorage on mount.
        <FinishScreen
          puzzle={puzzle}
          elapsedMs={finalElapsed}
          revealed={state.revealed}
          onClose={() => setFinishDismissed(true)}
        />
      )}
      {isFinished && finishDismissed && (
        <button
          type="button"
          onClick={() => setFinishDismissed(false)}
          style={{
            alignSelf: "flex-start",
            padding: "8px 14px",
            border: "1px solid #d9d9d6",
            borderRadius: 6,
            background: "#fff",
            cursor: "pointer",
            fontSize: 13,
          }}
        >
          Show finish summary
        </button>
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

// ---------------------------------------------------------------------------
// Splash overlay shown before the user clicks Start
// ---------------------------------------------------------------------------

function SplashOverlay({
  puzzleNumber,
  puzzleDate,
  onStart,
}: {
  puzzleNumber: number;
  puzzleDate: string;
  onStart: () => void;
}) {
  // Pretty date: "May 21" from "2026-05-21". Locale-aware formatting via
  // Intl, parsing the ISO date as a UTC date so the displayed month/day
  // doesn't shift across timezones.
  const pretty = useMemo(() => {
    const [y, m, d] = puzzleDate.split("-").map(Number);
    const dt = new Date(Date.UTC(y, m - 1, d));
    return new Intl.DateTimeFormat("en-US", {
      month: "long",
      day: "numeric",
      timeZone: "UTC",
    }).format(dt);
  }, [puzzleDate]);

  return (
    <div
      data-testid="splash-overlay"
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        // Subtle scrim so the blurred play surface reads as background.
        background:
          "radial-gradient(ellipse at center, rgba(255,253,246,0.4) 0%, rgba(255,253,246,0) 70%)",
        zIndex: 10,
      }}
    >
      <div
        style={{
          textAlign: "center",
          padding: "24px 28px",
          background: "rgba(255, 253, 246, 0.98)",
          borderRadius: 14,
          boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
          maxWidth: 320,
        }}
      >
        <div
          style={{
            fontSize: 11,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "#888",
            marginBottom: 4,
          }}
        >
          {pretty}
        </div>
        <h2
          style={{
            fontFamily: '"Iowan Old Style", "Charter", "Georgia", serif',
            fontSize: 26,
            margin: "0 0 16px",
            letterSpacing: "-0.01em",
          }}
        >
          NBA Mini #{puzzleNumber}
        </h2>
        <button
          type="button"
          onClick={onStart}
          autoFocus
          style={{
            background: "#c8102e",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            padding: "12px 32px",
            fontSize: 16,
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.02em",
            boxShadow: "0 4px 12px rgba(200, 16, 46, 0.35)",
          }}
        >
          Start
        </button>
      </div>
    </div>
  );
}
