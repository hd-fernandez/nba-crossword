"use client";

import { useEffect } from "react";

import { registerServiceWorker } from "@/lib/sw-register";

/**
 * Mount-time service worker registration. Renders nothing.
 *
 * Mounted in `app/layout.tsx` so registration runs on every route. The
 * `useEffect` ensures registration only happens client-side (never during
 * SSR/SSG) — `registerServiceWorker` no-ops in non-browser contexts as a
 * second guard, but the effect-only call also keeps the SSR HTML byte-identical
 * regardless of whether SW support is detected at request time.
 */
export function SwRegister(): null {
  useEffect(() => {
    // Fire-and-forget. The helper never throws; we don't need the result here.
    void registerServiceWorker();
  }, []);
  return null;
}
