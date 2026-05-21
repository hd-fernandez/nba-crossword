"use client";

import { useEffect, useMemo, useReducer, useRef, useState } from "react";

import { ClueBar } from "@/components/ClueBar";
import { FinishScreen } from "@/components/FinishScreen";
import { Grid, type GridHandle } from "@/components/Grid";
import { LeagueToggle } from "@/components/LeagueToggle";
import { StreakBadge } from "@/components/StreakBadge";
import { Timer } from "@/components/Timer";
import { configFor, otherLeague } from "@/lib/league";
import {
  fetchPuzzle,
  todayInEastern,
  type League,
  type Puzzle,
} from "@/lib/puzzle";
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

interface PuzzlePageProps {
  league: League;
}

/**
 * The shared per-league puzzle page. Mounted by `app/nba/page.tsx` and
 * `app/wnba/page.tsx` with the appropriate league. All league-specific
 * concerns — title, palette, hero photo, no-puzzle copy — flow from
 * {@link configFor} so this component itself stays a thin shell.
 *
 * Cross-league discovery: the header peeks at the *other* league's
 * puzzle availability for today and renders an "Also today" chip when
 * there's a fresh puzzle to switch to.
 */
export function PuzzlePage({ league }: PuzzlePageProps) {
  const cfg = configFor(league);
  const [status, setStatus] = useState<FetchStatus>({ kind: "loading" });
  const [today, setToday] = useState<string | null>(null);
  const [streak, setStreak] = useState<number>(0);
  const [otherLeagueAvailable, setOtherLeagueAvailable] =
    useState<Puzzle | null>(null);

  useEffect(() => {
    const t = todayInEastern();
    setToday(t);
    setStreak(getDisplayStreak(league, t));
  }, [league]);

  // Fetch this league's puzzle.
  useEffect(() => {
    if (!today) return;
    let cancelled = false;
    fetchPuzzle(league)
      .then((puzzle) => {
        if (cancelled) return;
        if (puzzle) {
          setStatus({ kind: "ready", puzzle });
        } else {
          markOffDay(league, today);
          setStreak(getDisplayStreak(league, today));
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
  }, [league, today]);

  // Fetch the *other* league's puzzle in parallel for the cross-league chip.
  // We only show the chip when there's actually something to discover; a 404
  // is fine and just means "no chip today."
  useEffect(() => {
    if (!today) return;
    const other = otherLeague(league);
    let cancelled = false;
    fetchPuzzle(other)
      .then((p) => {
        if (cancelled) return;
        setOtherLeagueAvailable(p);
      })
      .catch(() => {
        // Silent — discovery chip is non-essential, errors here shouldn't
        // disrupt the primary play surface.
      });
    return () => {
      cancelled = true;
    };
  }, [league, today]);

  return (
    <>
      {/* Photo backdrop — fixed-position so it doesn't repeat below long pages. */}
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          backgroundImage: `url(${cfg.heroPhoto})`,
          backgroundSize: "cover",
          backgroundPosition: "center",
          zIndex: -2,
          transition: "background-image 400ms ease",
        }}
      />
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          background: cfg.theme.overlayGradient,
          zIndex: -1,
        }}
      />
      <main
        style={{
          minHeight: "100vh",
          padding: "32px 16px 48px",
          fontFamily:
            'var(--font-sans, "Inter"), ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
          color: "#f7f7f5",
        }}
      >
        <div style={{ maxWidth: 540, margin: "0 auto" }}>
          <header
            style={{
              marginBottom: 12,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <h1
              style={{
                fontFamily:
                  'var(--font-serif, "Fraunces"), "Iowan Old Style", "Charter", "Georgia", serif',
                fontSize: 36,
                fontWeight: 600,
                margin: 0,
                letterSpacing: "-0.015em",
                color: "#fffdf6",
                textShadow: "0 1px 2px rgba(0,0,0,0.5)",
              }}
            >
              {cfg.title}
            </h1>
            <StreakBadge streak={streak} accent={cfg.theme.accent} />
          </header>

          <div
            style={{
              marginBottom: 24,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            <LeagueToggle current={league} />
            {otherLeagueAvailable && (
              <CrossLeagueChip
                otherLeague={otherLeagueAvailable.league}
                puzzleNumber={otherLeagueAvailable.puzzle_number}
              />
            )}
          </div>

          {status.kind === "loading" && (
            <div
              data-testid="loading"
              style={{
                background: "rgba(255, 253, 246, 0.06)",
                border: "1px solid rgba(255, 253, 246, 0.10)",
                borderRadius: 14,
                padding: "32px 20px",
                textAlign: "center",
                color: "rgba(247, 247, 245, 0.55)",
                fontSize: 13,
                letterSpacing: "0.04em",
                fontStyle: "italic",
              }}
            >
              Loading today&rsquo;s puzzle&hellip;
            </div>
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
              <p style={{ margin: 0 }}>{cfg.noPuzzleCopy}</p>
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
                accent={cfg.theme.accent}
                accentShadow={cfg.theme.accentShadow}
                onCompletion={() => {
                  if (today) setStreak(getStreak(league, today));
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

function CrossLeagueChip({
  otherLeague: ol,
  puzzleNumber,
}: {
  otherLeague: League;
  puzzleNumber: number;
}) {
  const cfg = configFor(ol);
  return (
    <a
      href={`/${ol}`}
      data-testid="cross-league-chip"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        fontSize: 12,
        padding: "5px 10px",
        borderRadius: 999,
        background: "rgba(255, 253, 246, 0.12)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        border: "1px solid rgba(255, 253, 246, 0.18)",
        color: "#fffdf6",
        textDecoration: "none",
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ opacity: 0.65 }}>Also today</span>
      <span
        aria-hidden
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: cfg.theme.accent,
          boxShadow: `0 0 6px ${cfg.theme.accentShadow}`,
        }}
      />
      <span style={{ fontWeight: 600 }}>
        {cfg.splashTitlePrefix} #{puzzleNumber}
      </span>
    </a>
  );
}

function PuzzleView({
  puzzle,
  accent,
  accentShadow,
  onCompletion,
}: {
  puzzle: Puzzle;
  accent: string;
  accentShadow: string;
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
    requestAnimationFrame(() => gridRef.current?.focus());
  }

  const isFinished = state.finishedAt !== null;
  const [finishDismissed, setFinishDismissed] = useState(false);
  const finalElapsed = useMemo(
    () => (isFinished ? elapsedMs(state, Date.now()) : 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [isFinished, state.finishedAt],
  );

  useEffect(() => {
    if (!isFinished) return;
    onCompletion?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isFinished, state.finishedAt]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 16,
        position: "relative",
      }}
    >
      <div
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
          league={puzzle.league}
          accent={accent}
          accentShadow={accentShadow}
          onStart={handleStart}
        />
      )}

      {started && isFinished && !finishDismissed && (
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

function SplashOverlay({
  puzzleNumber,
  puzzleDate,
  league,
  accent,
  accentShadow,
  onStart,
}: {
  puzzleNumber: number;
  puzzleDate: string;
  league: League;
  accent: string;
  accentShadow: string;
  onStart: () => void;
}) {
  const cfg = configFor(league);
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
        background:
          "radial-gradient(ellipse at center, rgba(255,253,246,0.4) 0%, rgba(255,253,246,0) 70%)",
        zIndex: 10,
      }}
    >
      <div
        style={{
          textAlign: "center",
          padding: "28px 28px 24px",
          background: "rgba(255, 253, 246, 0.98)",
          borderRadius: 14,
          boxShadow: "0 12px 40px rgba(0,0,0,0.25)",
          maxWidth: 320,
        }}
      >
        <div
          style={{
            fontSize: 11,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: "#888",
            marginBottom: 6,
          }}
        >
          {pretty}
        </div>
        <h2
          style={{
            fontFamily:
              'var(--font-serif, "Fraunces"), "Iowan Old Style", "Charter", "Georgia", serif',
            fontSize: 30,
            fontWeight: 600,
            margin: "0 0 4px",
            letterSpacing: "-0.015em",
          }}
        >
          {cfg.splashTitlePrefix} #{puzzleNumber}
        </h2>
        <p
          style={{
            margin: "0 0 18px",
            fontSize: 12,
            color: "#888",
            letterSpacing: "0.01em",
          }}
        >
          A daily 5×5 from yesterday&rsquo;s slate.
        </p>
        <button
          type="button"
          onClick={onStart}
          autoFocus
          style={{
            background: accent,
            color: "#fff",
            border: "none",
            borderRadius: 999,
            padding: "12px 36px",
            fontSize: 16,
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "0.02em",
            boxShadow: `0 4px 14px ${accentShadow}`,
            transition: "transform 120ms ease, box-shadow 120ms ease",
          }}
          onMouseDown={(e) => {
            e.currentTarget.style.transform = "scale(0.98)";
          }}
          onMouseUp={(e) => {
            e.currentTarget.style.transform = "scale(1)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.transform = "scale(1)";
          }}
        >
          Start
        </button>
      </div>
    </div>
  );
}
