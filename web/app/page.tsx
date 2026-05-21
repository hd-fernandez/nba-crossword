"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { inSeasonLeague } from "@/lib/league";
import { getLastPlayedLeague } from "@/lib/storage";

/**
 * Smart redirect at `/` — picks a default league per the rules from the
 * multi-league brainstorm:
 *
 *   1. Sticky preference: if the user has played either league before,
 *      route them to that league.
 *   2. Cold start: route by calendar (in-season league wins; NBA on
 *      cold-start in the May overlap month).
 *
 * The redirect runs client-side because it depends on `localStorage`,
 * which is only available after hydration. SSR delivers a tiny shell
 * with a brief loading state; the client takes over and replaces the
 * URL within a frame.
 */
export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    const sticky = getLastPlayedLeague();
    const target = sticky ?? inSeasonLeague();
    router.replace(`/${target}`);
  }, [router]);

  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#0a0a0c",
        color: "rgba(247, 247, 245, 0.6)",
        fontFamily:
          'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
        fontSize: 14,
        letterSpacing: "0.04em",
      }}
    >
      Loading the Mini&hellip;
    </main>
  );
}
