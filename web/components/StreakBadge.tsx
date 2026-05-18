"use client";

/**
 * Tiny chip-style badge for the page header.
 *
 * Pure presentation: takes a `streak` number and renders 🔥 N when positive,
 * a subtle "Start your streak" prompt when zero. The page is responsible for
 * computing the streak (via `getStreak()`); we keep this component dumb so
 * it's trivial to test and so the page can re-compute on completion.
 */
interface StreakBadgeProps {
  streak: number;
}

export function StreakBadge({ streak }: StreakBadgeProps) {
  if (streak <= 0) {
    return (
      <span
        data-testid="streak-badge"
        data-streak="0"
        aria-label="No active streak yet"
        style={{
          fontSize: 12,
          color: "#888",
          fontStyle: "italic",
          userSelect: "none",
        }}
      >
        Start your streak
      </span>
    );
  }

  return (
    <span
      data-testid="streak-badge"
      data-streak={String(streak)}
      aria-label={`Current streak: ${streak} day${streak === 1 ? "" : "s"}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "4px 10px",
        background: "#fff5e6",
        border: "1px solid #f0c878",
        borderRadius: 999,
        fontSize: 13,
        fontWeight: 600,
        color: "#7a4a00",
        fontVariantNumeric: "tabular-nums",
        userSelect: "none",
      }}
    >
      <span aria-hidden>🔥</span>
      <span data-testid="streak-badge-count">{streak}</span>
    </span>
  );
}
