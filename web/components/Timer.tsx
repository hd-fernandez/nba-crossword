"use client";

import { useEffect, useState } from "react";

import { type SolveState, elapsedMs } from "@/lib/state";
import { formatElapsed } from "@/lib/share";

interface TimerProps {
  state: SolveState;
}

/**
 * Visible elapsed-time readout with a "hide" toggle.
 *
 * The reducer state owns the timer *anchor* (`startedAt`, `accumulatedMs`,
 * `finishedAt`). This component:
 *   - reads those three fields,
 *   - re-renders itself once a second via `setInterval`,
 *   - computes the displayed elapsed value from the anchor on each render.
 *
 * That keeps action churn out of the reducer (no per-second `tick`
 * dispatches) and keeps the elapsed value testable as a pure function of
 * (state, now).
 *
 * Hiding the timer is a *display-only* toggle — the underlying anchor keeps
 * advancing, so revealing it again shows the correct value.
 */
export function Timer({ state }: TimerProps) {
  const [, forceTick] = useState(0);
  const [hidden, setHidden] = useState(false);

  // Tick once a second while running. We don't tick after finish (frozen)
  // or before first input (no anchor yet).
  const isRunning = state.startedAt !== null && state.finishedAt === null;
  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [isRunning]);

  const display = formatElapsed(elapsedMs(state, Date.now()));

  return (
    <div
      data-testid="timer"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
        fontSize: 14,
        color: "#444",
      }}
    >
      <span
        data-testid="timer-value"
        aria-label={hidden ? "Timer hidden" : `Elapsed time ${display}`}
        style={{
          minWidth: 44,
          fontVariantNumeric: "tabular-nums",
          fontWeight: 600,
          color: hidden ? "transparent" : "#1a1a1a",
          // Keep the layout stable when hidden — hide via opacity-equivalent.
          background: hidden ? "#e8e6df" : "transparent",
          borderRadius: 4,
          padding: "2px 6px",
          userSelect: "none",
        }}
      >
        {display}
      </span>
      <button
        type="button"
        data-testid="timer-toggle"
        onClick={() => setHidden((h) => !h)}
        aria-pressed={hidden}
        style={{
          fontSize: 11,
          color: "#555",
          background: "transparent",
          border: "1px solid #c4c1b6",
          borderRadius: 4,
          padding: "2px 8px",
          cursor: "pointer",
        }}
      >
        {hidden ? "Show" : "Hide"}
      </button>
    </div>
  );
}
