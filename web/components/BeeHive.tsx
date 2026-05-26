"use client";

import { useMemo } from "react";

import type { BeePuzzle } from "@/lib/bee";

interface BeeHiveProps {
  puzzle: BeePuzzle;
  /** Display order of the 6 outer letters. Pass a freshly-shuffled copy
   *  to "shuffle" the board visually. */
  outerOrder: string[];
  /** Called when any board letter is clicked or tapped. */
  onTapLetter: (letter: string) => void;
  /** Accent color for the center cell. */
  accent: string;
}

/**
 * Six outer hexagons arranged in a flat-top honeycomb around a center
 * hexagon — same layout as NYT Spelling Bee.
 *
 * Hex math (flat-top, flat side up):
 *   circumradius (vertex distance) = R
 *   width  = 2 * R
 *   height = sqrt(3) * R
 *   neighbor distance = R * sqrt(3) + GAP (edge-to-edge contact, plus the gap)
 *   neighbor angles   = 0°, 60°, 120°, 180°, 240°, 300°
 *
 * Flat-top is what NYT uses: flat side at top and bottom of each hex,
 * vertices on the left and right. Six neighbors sit directly above/below
 * and at 60° offsets — produces the "flower" pattern of two hexes left,
 * two hexes right, one above, one below the center.
 */
export function BeeHive({ puzzle, outerOrder, onTapLetter, accent }: BeeHiveProps) {
  // Hex radius (circumradius) in SVG units. Bigger = bigger hexes.
  const R = 50;
  // Gap between adjacent hexes. Tiny so the honeycomb reads as a unit.
  const GAP = 3;

  // Edge-to-edge distance for flat-top hexes is sqrt(3)*R (their inradius
  // doubled). Add the gap so they don't touch.
  const neighborDistance = R * Math.sqrt(3) + GAP;

  const positions = useMemo(() => {
    // Six positions around the center for a flat-top honeycomb. Looking
    // at the NYT layout: one hex straight up, one straight down, two on
    // each side at 30° above/below horizontal. That maps to angles
    // 90° (top), 30°, -30°, -90° (bottom), -150°, 150° measured from
    // positive-x going counter-clockwise. In SVG (y-down), we negate the
    // y component.
    const angles = [90, 30, -30, -90, -150, 150]; // top, then clockwise
    return angles.map((deg) => {
      const rad = (deg * Math.PI) / 180;
      return {
        dx: neighborDistance * Math.cos(rad),
        // SVG y-axis points down; negate so 90° = up
        dy: -neighborDistance * Math.sin(rad),
      };
    });
  }, [neighborDistance]);

  // ViewBox sizing: the hive's full extent is (center hex) + the
  // farthest neighbor's own extent. For flat-top hexes the vertical
  // reach is sqrt(3)/2 * R, the horizontal is R. We use the neighbor
  // distance plus the appropriate hex extent on each axis.
  const PADDING = 12;
  const halfH = neighborDistance + (R * Math.sqrt(3)) / 2 + PADDING;
  const halfW = neighborDistance + R + PADDING;
  const VIEW_W = halfW * 2;
  const VIEW_H = halfH * 2;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      width="100%"
      style={{
        maxWidth: 360,
        display: "block",
        margin: "0 auto",
        userSelect: "none",
      }}
      data-testid="bee-hive"
    >
      {/* Outer hexes — drawn first so the center sits on top of any overlap. */}
      {positions.map((pos, i) => {
        const letter = outerOrder[i];
        if (!letter) return null;
        return (
          <Hex
            key={`outer-${i}`}
            cx={halfW + pos.dx}
            cy={halfH + pos.dy}
            size={R}
            letter={letter}
            isCenter={false}
            onTap={() => onTapLetter(letter)}
            accent={accent}
          />
        );
      })}
      {/* Center hex */}
      <Hex
        cx={halfW}
        cy={halfH}
        size={R}
        letter={puzzle.center_letter}
        isCenter
        onTap={() => onTapLetter(puzzle.center_letter)}
        accent={accent}
      />
    </svg>
  );
}

interface HexProps {
  cx: number;
  cy: number;
  size: number;
  letter: string;
  isCenter: boolean;
  onTap: () => void;
  accent: string;
}

/** A single flat-top hexagon, click-able. */
function Hex({ cx, cy, size, letter, isCenter, onTap, accent }: HexProps) {
  // Flat-top hexagon vertices at angles 0°, 60°, 120°, 180°, 240°, 300°.
  // Two vertices on the horizontal (left and right edges); flat side at
  // the top and bottom.
  const points = useMemo(() => {
    const angles = [0, 60, 120, 180, 240, 300];
    return angles
      .map((deg) => {
        const rad = (deg * Math.PI) / 180;
        // SVG y-axis points down; negate sin so positive-y is up in math sense.
        const x = cx + size * Math.cos(rad);
        const y = cy - size * Math.sin(rad);
        return `${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [cx, cy, size]);

  return (
    <g
      onClick={onTap}
      onMouseDown={(e) => e.preventDefault()} // don't steal focus
      style={{ cursor: "pointer" }}
      data-testid={`bee-hex-${letter}`}
      data-center={isCenter ? "true" : "false"}
    >
      <polygon
        points={points}
        fill={isCenter ? accent : "#f4f1ea"}
        stroke={isCenter ? accent : "#d6d3c8"}
        strokeWidth={1.5}
        style={{ transition: "fill 120ms ease, transform 120ms ease" }}
      />
      <text
        x={cx}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize={size * 0.6}
        fontWeight={700}
        fill={isCenter ? "#fff" : "#1a1a1a"}
        style={{
          fontFamily:
            'var(--font-sans), ui-sans-serif, system-ui, sans-serif',
          pointerEvents: "none",
        }}
      >
        {letter}
      </text>
    </g>
  );
}
