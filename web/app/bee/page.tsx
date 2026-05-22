"use client";

import { BeePage } from "@/components/BeePage";

// Combined-corpus Bee. v3 launch ships only the per-league flavors with
// real puzzle JSON; the `/bee` route renders the same shell with the
// "combined" league and will show the dormant state until we add a
// combined corpus + generator pass (post-v3).
export default function BeeIndexPage() {
  return <BeePage league="combined" />;
}
