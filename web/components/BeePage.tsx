"use client";

import { useEffect, useMemo, useReducer, useState } from "react";

import { BeeHive } from "@/components/BeeHive";
import { LeagueToggle } from "@/components/LeagueToggle";
import { configFor } from "@/lib/league";
import {
  scoreName,
  tierForScore,
  type BeeLeague,
  type BeePuzzle,
  type TierKey,
} from "@/lib/bee";
import { fetchBee } from "@/lib/bee-fetch";
import {
  beeReducer,
  initialBeeState,
  isBeeSolved,
  scoreState,
  type BeeAction,
  type BeeState,
  type EntryFeedback,
} from "@/lib/bee-state";
import { todayInEastern } from "@/lib/puzzle";

type BeeFetchStatus =
  | { kind: "loading" }
  | { kind: "ready"; puzzle: BeePuzzle }
  | { kind: "no-bee" }
  | { kind: "error"; message: string };

interface BeePageProps {
  league: BeeLeague;
}

const TIER_LABELS: Record<TierKey, string> = {
  g_league_callup: "G League Call-Up",
  rookie: "Rookie",
  sophomore: "Sophomore",
  vet: "Vet",
  all_star: "All-Star",
  champion: "Champion",
  hall_of_famer: "Hall of Famer",
  goat: "GOAT",
};

/**
 * The shared per-league Bee page. NBA at /nba/bee, WNBA at /wnba/bee,
 * combined at /bee. All three flavors render this same component with a
 * different `league`.
 */
export function BeePage({ league }: BeePageProps) {
  // For the combined Bee, fall back to NBA's accent for now — we don't
  // have a third palette in `lib/league.ts` yet. The combined identity
  // (gold? a third color?) is a v3.5 polish question.
  const cfg = league === "combined" ? configFor("nba") : configFor(league);
  const accent = cfg.theme.accent;

  const [status, setStatus] = useState<BeeFetchStatus>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    fetchBee(league)
      .then((puzzle) => {
        if (cancelled) return;
        setStatus(puzzle ? { kind: "ready", puzzle } : { kind: "no-bee" });
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
  }, [league]);

  return (
    <>
      <div
        aria-hidden
        style={{
          position: "fixed",
          inset: 0,
          backgroundImage: `url(${cfg.heroPhoto})`,
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
          background: cfg.theme.overlayGradient,
          zIndex: -1,
        }}
      />
      <main
        style={{
          minHeight: "100vh",
          padding: "32px 16px 48px",
          color: "#f7f7f5",
          fontFamily:
            'var(--font-sans), ui-sans-serif, system-ui, sans-serif',
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
                  'var(--font-serif), "Iowan Old Style", Georgia, serif',
                fontSize: 36,
                fontWeight: 600,
                margin: 0,
                letterSpacing: "-0.015em",
                color: "#fffdf6",
                textShadow: "0 1px 2px rgba(0,0,0,0.5)",
              }}
            >
              Hoops Bee
            </h1>
          </header>

          <div
            style={{
              marginBottom: 18,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
            }}
          >
            {league !== "combined" && <LeagueToggle current={league} />}
            <a
              href={`/${league === "combined" ? "" : league}`}
              style={{
                fontSize: 12,
                color: "rgba(255,253,246,0.7)",
                textDecoration: "none",
                letterSpacing: "0.04em",
              }}
            >
              ← Back to crossword
            </a>
          </div>

          {status.kind === "loading" && (
            <div
              style={{
                background: "rgba(255,253,246,0.06)",
                border: "1px solid rgba(255,253,246,0.10)",
                borderRadius: 14,
                padding: "32px 20px",
                textAlign: "center",
                color: "rgba(247,247,245,0.55)",
                fontSize: 13,
                fontStyle: "italic",
              }}
            >
              Loading today&rsquo;s Bee&hellip;
            </div>
          )}

          {status.kind === "no-bee" && (
            <div
              role="status"
              data-testid="no-bee"
              style={{
                background: "rgba(255,253,246,0.96)",
                color: "#1a1a1a",
                borderRadius: 12,
                padding: 24,
                boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
              }}
            >
              <h2 style={{ marginTop: 0 }}>No Bee today</h2>
              <p style={{ margin: 0 }}>Check back tomorrow.</p>
            </div>
          )}

          {status.kind === "error" && (
            <div
              role="alert"
              style={{
                color: "#fff",
                background: "rgba(160,0,0,0.85)",
                padding: 16,
                borderRadius: 8,
              }}
            >
              Couldn&rsquo;t load today&rsquo;s Bee: {status.message}
            </div>
          )}

          {status.kind === "ready" && (
            <BeeBoard puzzle={status.puzzle} accent={accent} />
          )}

          <footer
            style={{
              marginTop: 24,
              fontSize: 11,
              color: "rgba(247,247,245,0.55)",
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

function BeeBoard({ puzzle, accent }: { puzzle: BeePuzzle; accent: string }) {
  const reducer = useMemo(() => beeReducer(puzzle), [puzzle]);
  const [state, dispatch] = useReducer(reducer, initialBeeState());

  // Outer letters get a stable initial order, but the user can shuffle.
  // We track the order in a `useState` outside the reducer because shuffles
  // are a pure presentation concern and don't affect any derived state.
  const [outerOrder, setOuterOrder] = useState<string[]>(puzzle.outer_letters);
  const onShuffle = () => {
    const next = [...outerOrder];
    // Fisher-Yates one-pass.
    for (let i = next.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [next[i], next[j]] = [next[j], next[i]];
    }
    setOuterOrder(next);
    dispatch({ type: "shuffle" });
  };

  // Keyboard input. Listen on the page (not on a specific element) so the
  // user doesn't have to focus anything.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key;
      if (/^[a-zA-Z]$/.test(k)) {
        dispatch({ type: "type", letter: k });
        e.preventDefault();
      } else if (k === "Backspace") {
        dispatch({ type: "delete" });
        e.preventDefault();
      } else if (k === "Enter") {
        dispatch({ type: "submit" });
        e.preventDefault();
      } else if (k === "Escape") {
        dispatch({ type: "clearEntry" });
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const score = scoreState(puzzle, state);
  const tier = tierForScore(score, puzzle.tier_thresholds, puzzle.max_score);
  const solved = isBeeSolved(puzzle, state);

  return (
    <div
      style={{
        background: "rgba(255,253,246,0.97)",
        color: "#1a1a1a",
        borderRadius: 14,
        padding: 20,
        boxShadow: "0 16px 50px rgba(0,0,0,0.4)",
      }}
    >
      {/* Tier + score row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 12,
          marginBottom: 16,
        }}
      >
        <div>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#888",
              marginBottom: 2,
            }}
          >
            Tier
          </div>
          <div
            data-testid="bee-tier"
            style={{
              fontFamily: 'var(--font-serif), Georgia, serif',
              fontSize: 22,
              fontWeight: 600,
              color: tier ? "#1a1a1a" : "#aaa",
            }}
          >
            {tier ? TIER_LABELS[tier] : "Undrafted"}
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: "#888",
              marginBottom: 2,
            }}
          >
            Score
          </div>
          <div
            data-testid="bee-score"
            style={{
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              fontSize: 20,
              fontWeight: 700,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {score} / {puzzle.max_score}
          </div>
        </div>
      </div>

      {/* Entry bar */}
      <EntryBar entry={state.entry} feedback={state.lastFeedback} feedbackKey={state.feedbackKey} />

      {/* Hexagon hive */}
      <div style={{ margin: "20px 0" }}>
        <BeeHive
          puzzle={puzzle}
          outerOrder={outerOrder}
          onTapLetter={(l) => dispatch({ type: "tap", letter: l })}
          accent={accent}
        />
      </div>

      {/* Action buttons */}
      <div
        style={{
          display: "flex",
          gap: 8,
          justifyContent: "center",
          marginBottom: 16,
        }}
      >
        <ActionButton onClick={() => dispatch({ type: "delete" })} label="Delete" />
        <ActionButton onClick={onShuffle} label="Shuffle" />
        <ActionButton
          onClick={() => dispatch({ type: "submit" })}
          label="Enter"
          accent={accent}
        />
      </div>

      {/* Found names list */}
      <FoundList
        found={state.found}
        valid={puzzle.valid_names}
        pangrams={puzzle.pangrams}
      />

      {solved && (
        <div
          role="status"
          data-testid="bee-solved"
          style={{
            marginTop: 16,
            padding: 12,
            background: "#fff5d6",
            border: "1px solid #f0c878",
            borderRadius: 8,
            fontSize: 14,
            textAlign: "center",
            color: "#7a4a00",
            fontWeight: 600,
          }}
        >
          🎉 Every name found — GOAT tier.
        </div>
      )}
    </div>
  );
}

function EntryBar({
  entry,
  feedback,
  feedbackKey,
}: {
  entry: string;
  feedback: EntryFeedback | null;
  feedbackKey: number;
}) {
  const placeholderShown = entry.length === 0;
  const message = feedback ? feedbackToMessage(feedback) : null;
  return (
    <div
      data-testid="bee-entry-bar"
      style={{
        position: "relative",
        textAlign: "center",
        minHeight: 44,
        padding: "10px 12px",
        fontFamily: "var(--font-sans), system-ui, sans-serif",
        fontSize: 22,
        fontWeight: 700,
        letterSpacing: "0.04em",
        color: placeholderShown ? "#bdbab2" : "#1a1a1a",
      }}
    >
      {placeholderShown ? "Type a name" : entry}
      {message && (
        <div
          key={feedbackKey}
          data-testid="bee-feedback"
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: "100%",
            marginTop: 4,
            fontSize: 12,
            fontWeight: 500,
            letterSpacing: "0.03em",
            color: message.color,
          }}
        >
          {message.text}
        </div>
      )}
    </div>
  );
}

function feedbackToMessage(f: EntryFeedback): { text: string; color: string } {
  switch (f.kind) {
    case "ok":
      return {
        text: f.isPangram
          ? `+${f.pointsGained} — Pangram! 🐝`
          : `+${f.pointsGained}`,
        color: "#2e7d32",
      };
    case "tooShort":
      return { text: "Too short", color: "#888" };
    case "missingCenter":
      return { text: "Must include the center letter", color: "#888" };
    case "badLetters":
      return { text: "Letters not on the board", color: "#888" };
    case "alreadyFound":
      return { text: "Already found", color: "#888" };
    case "notInList":
      return { text: "Not in our list", color: "#a04040" };
  }
}

function ActionButton({
  onClick,
  label,
  accent,
}: {
  onClick: () => void;
  label: string;
  accent?: string;
}) {
  const isPrimary = !!accent;
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={`bee-action-${label.toLowerCase()}`}
      style={{
        padding: "10px 18px",
        borderRadius: 999,
        border: isPrimary ? "none" : "1px solid #d6d3c8",
        background: isPrimary ? accent : "#fff",
        color: isPrimary ? "#fff" : "#333",
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        cursor: "pointer",
        boxShadow: isPrimary ? `0 3px 10px ${accent}55` : "none",
      }}
    >
      {label}
    </button>
  );
}

function FoundList({
  found,
  valid,
  pangrams,
}: {
  found: string[];
  valid: string[];
  pangrams: string[];
}) {
  const [open, setOpen] = useState(false);
  const pangramSet = new Set(pangrams);
  return (
    <div data-testid="bee-found-list">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        style={{
          width: "100%",
          padding: "8px 12px",
          background: "#f4f1ea",
          border: "1px solid #e0dccd",
          borderRadius: 8,
          fontSize: 13,
          textAlign: "left",
          cursor: "pointer",
          color: "#333",
          fontFamily: "var(--font-sans), system-ui, sans-serif",
        }}
      >
        Found {found.length} of {valid.length}{" "}
        <span style={{ color: "#999", fontWeight: 400 }}>
          ({open ? "hide" : "show"})
        </span>
      </button>
      {open && (
        <ul
          style={{
            margin: "8px 0 0",
            padding: "8px 12px",
            background: "#fffdf6",
            border: "1px solid #e8e6df",
            borderRadius: 8,
            listStyle: "none",
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            fontSize: 13,
          }}
        >
          {found.length === 0 && (
            <li style={{ color: "#999", fontStyle: "italic" }}>
              Names you find will appear here.
            </li>
          )}
          {found.map((name) => (
            <li
              key={name}
              style={{
                fontWeight: pangramSet.has(name) ? 700 : 500,
                color: pangramSet.has(name) ? "#7a4a00" : "#333",
              }}
            >
              {name}
              {pangramSet.has(name) && " 🐝"}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
