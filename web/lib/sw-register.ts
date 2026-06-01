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

import { BASE_PATH } from "./base-path";

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
  // Never run the service worker in development. A cache-first SW serves the
  // stale built shell instead of the dev server's fresh bundle, which forces a
  // hard reload (cmd+shift+R) on every load. Worse, a SW installed during a
  // *previous* prod-mode session lingers in the browser and keeps doing this
  // even after we stop registering — so in dev we actively unregister any
  // existing SW and wipe its caches, self-healing the developer's browser.
  if (process.env.NODE_ENV !== "production") {
    await unregisterServiceWorkers();
    return { kind: "skipped", reason: "dev-mode" };
  }

  try {
    // Under a subpath deploy (GitHub Pages) both the SW URL and its scope are
    // prefixed with BASE_PATH; at the root they're "/sw.js" + "/" as before.
    // The SW can only control URLs at or below its own path, so the scope must
    // match the prefix the app is actually served from.
    const registration = await navigator.serviceWorker.register(`${BASE_PATH}/sw.js`, {
      scope: `${BASE_PATH}/`,
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

/**
 * Tear down any service worker this origin previously installed, plus the
 * caches it created. Used in development so a SW from an earlier prod-mode
 * run can't keep serving a stale shell. Best-effort: never throws.
 */
async function unregisterServiceWorkers(): Promise<void> {
  try {
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((r) => r.unregister()));
    if ("caches" in window) {
      const keys = await caches.keys();
      await Promise.all(keys.map((key) => caches.delete(key)));
    }
  } catch (error) {
    // eslint-disable-next-line no-console
    console.warn("[sw-register] dev cleanup failed", error);
  }
}
