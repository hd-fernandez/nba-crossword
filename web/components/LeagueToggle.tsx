"use client";

import Link from "next/link";

import { ALL_LEAGUES, configFor } from "@/lib/league";
import type { League } from "@/lib/puzzle";

interface LeagueToggleProps {
  current: League;
}

/**
 * Two-segment pill toggle: NBA · WNBA. The non-current segment is a link
 * to the other league's page; the current segment is rendered as a span
 * with the league's accent color and a subtle filled background.
 *
 * One click, no confirmation, no JS-driven nav — just an <a> tag. That
 * keeps Next's prefetching working and means the toggle behaves identically
 * with or without JS hydrated.
 */
export function LeagueToggle({ current }: LeagueToggleProps) {
  return (
    <div
      role="tablist"
      aria-label="League"
      data-testid="league-toggle"
      style={{
        display: "inline-flex",
        padding: 3,
        borderRadius: 999,
        background: "rgba(255, 253, 246, 0.10)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        border: "1px solid rgba(255, 253, 246, 0.18)",
      }}
    >
      {ALL_LEAGUES.map((l) => {
        const cfg = configFor(l);
        const active = l === current;
        const label = l.toUpperCase();
        const baseStyle: React.CSSProperties = {
          display: "inline-flex",
          alignItems: "center",
          padding: "5px 14px",
          fontSize: 12,
          fontWeight: 700,
          letterSpacing: "0.06em",
          borderRadius: 999,
          textDecoration: "none",
          transition: "background 160ms ease, color 160ms ease",
        };
        if (active) {
          return (
            <span
              key={l}
              role="tab"
              aria-selected="true"
              data-testid={`league-toggle-${l}`}
              data-active="true"
              style={{
                ...baseStyle,
                background: cfg.theme.accent,
                color: "#fff",
                boxShadow: `0 2px 8px ${cfg.theme.accentShadow}`,
              }}
            >
              {label}
            </span>
          );
        }
        return (
          <Link
            key={l}
            href={`/${l}`}
            role="tab"
            aria-selected="false"
            data-testid={`league-toggle-${l}`}
            data-active="false"
            style={{
              ...baseStyle,
              color: "rgba(255, 253, 246, 0.7)",
            }}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
