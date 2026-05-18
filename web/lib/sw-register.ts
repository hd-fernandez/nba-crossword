/**
 * Service worker registration helper.
 *
 * Kept separate from the React component so the registration logic is
 * testable in isolation and so future tweaks (e.g., explicit update flow,
 * push subscription) don't bloat the layout-mounted component.
 *
 * Behavior:
 *   - No-op on the server, in non-secure contexts, or in browsers without
 *     `serviceWorker` support. The PWA degrades to a regular web app.
 *   - We deliberately register `/sw.js` with `scope: "/"` so the SW controls
 *     the entire origin (puzzles, app shell, icons, future routes).
 *   - Errors are logged but never thrown — a busted SW must never take the
 *     app down. The user still gets a working web page.
 */

export type SwRegisterResult =
  | { kind: "registered"; registration: ServiceWorkerRegistration }
  | { kind: "skipped"; reason: string }
  | { kind: "error"; error: unknown };

export async function registerServiceWorker(): Promise<SwRegisterResult> {
  if (typeof window === "undefined") {
    return { kind: "skipped", reason: "no-window" };
  }
  if (!("serviceWorker" in navigator)) {
    return { kind: "skipped", reason: "unsupported" };
  }
  // SW requires a secure context. localhost is treated as secure by browsers,
  // so dev still works; only http://<lan-ip> kinds of setups skip.
  if (!window.isSecureContext) {
    return { kind: "skipped", reason: "insecure-context" };
  }

  try {
    const registration = await navigator.serviceWorker.register("/sw.js", {
      scope: "/",
      // `updateViaCache: "none"` makes the browser bypass HTTP caches when
      // checking for an updated `sw.js`, so a deploy with a bumped
      // CACHE_VERSION rolls out promptly. Vercel headers also force
      // no-cache on `/sw.js` for the same reason — this is defense in depth.
      updateViaCache: "none",
    });
    return { kind: "registered", registration };
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn("[sw-register] registration failed", error);
    return { kind: "error", error };
  }
}
