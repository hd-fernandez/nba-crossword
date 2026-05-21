"use client";

/**
 * Tiny chip-style badge for the page header.
 *
 * Pure presentation: takes a `streak` number and renders 🔥 N when positive,
 * a subtle "Start your streak" prompt when zero. The page is responsible for
 * computing the streak; we keep this component dumb so it's trivial to test
 * and so the page can re-compute on completion.
 *
 * Accepts an optional `accent` color so per-league theming can flow through
 * — NBA (red) and WNBA (orange) get visually distinct streak chips even
 * when the streak count is the same.
 */
interface StreakBadgeProps {
  streak: number;
  /** Hex accent color used for the chip background tint. Optional. */
  accent?: string;
}

/** Mix a hex color with white to produce a soft tint. */
function tint(hex: string, amount: number): string {
  // Parse #RRGGBB
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return "#fff5e6";
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 0xff;
  const g = (n >> 8) & 0xff;
  const b = n & 0xff;
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  return `rgb(${mix(r)}, ${mix(g)}, ${mix(b)})`;
}

export function StreakBadge({ streak, accent }: StreakBadgeProps) {
  if (streak <= 0) {
    return (
      <span
        data-testid="streak-badge"
        data-streak="0"
        aria-label="No active streak yet"
        style={{
          fontSize: 12,
          color: "rgba(247, 247, 245, 0.6)",
          fontStyle: "italic",
          userSelect: "none",
        }}
      >
        Start your streak
      </span>
    );
  }

  const bg = accent ? tint(accent, 0.85) : "#fff5e6";
  const border = accent ? tint(accent, 0.5) : "#f0c878";
  const fg = accent ?? "#7a4a00";

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
        background: bg,
        border: `1px solid ${border}`,
        borderRadius: 999,
        fontSize: 13,
        fontWeight: 600,
        color: fg,
        fontVariantNumeric: "tabular-nums",
        userSelect: "none",
      }}
    >
      <span aria-hidden>🔥</span>
      <span data-testid="streak-badge-count">{streak}</span>
    </span>
  );
}
