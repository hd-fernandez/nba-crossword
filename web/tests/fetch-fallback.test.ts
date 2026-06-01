import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { fetchLatestPuzzle } from "@/lib/puzzle";
import { fetchLatestBee } from "@/lib/bee-fetch";

const ROOT = resolve(__dirname, "../..");
const NBA_PUZZLE = readFileSync(
  resolve(ROOT, "puzzles/nba/2026-05-29.json"),
  "utf-8",
);
const NBA_BEE = readFileSync(
  resolve(ROOT, "puzzles/nba/bee/2026-05-29.json"),
  "utf-8",
);

function ok(body: string): Response {
  return new Response(body, { status: 200 });
}
function notFound(): Response {
  return new Response("not found", { status: 404 });
}

/**
 * Build a fetch stub from a path → Response map. Any path not in the map
 * resolves to a 404, modeling a static host where missing files just 404.
 */
function stubFetch(routes: Record<string, () => Response>): typeof fetch {
  return (async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const path = url.split("?")[0];
    const handler = routes[path];
    return handler ? handler() : notFound();
  }) as typeof fetch;
}

describe("fetchLatestPuzzle", () => {
  it("returns today's puzzle when it exists (isToday=true)", async () => {
    const fetchImpl = stubFetch({
      "/puzzles/nba/2026-05-29.json": () => ok(NBA_PUZZLE),
    });
    const resolved = await fetchLatestPuzzle("nba", "2026-05-29", fetchImpl);
    expect(resolved).not.toBeNull();
    expect(resolved!.isToday).toBe(true);
    expect(resolved!.date).toBe("2026-05-29");
  });

  it("falls back to the latest indexed puzzle when today's is missing", async () => {
    const fetchImpl = stubFetch({
      // today (2026-06-01) is absent → 404
      "/puzzles/nba/index.json": () =>
        ok(
          JSON.stringify({
            dates: ["2026-05-29", "2026-05-26", "2026-05-21"],
            latest: "2026-05-29",
          }),
        ),
      "/puzzles/nba/2026-05-29.json": () => ok(NBA_PUZZLE),
    });
    const resolved = await fetchLatestPuzzle("nba", "2026-06-01", fetchImpl);
    expect(resolved).not.toBeNull();
    expect(resolved!.isToday).toBe(false);
    expect(resolved!.date).toBe("2026-05-29");
  });

  it("never picks a future-dated puzzle as the fallback", async () => {
    const fetchImpl = stubFetch({
      "/puzzles/nba/index.json": () =>
        ok(
          JSON.stringify({
            // 2026-12-25 is in the future relative to `today` below.
            dates: ["2026-12-25", "2026-05-29"],
            latest: "2026-12-25",
          }),
        ),
      "/puzzles/nba/2026-05-29.json": () => ok(NBA_PUZZLE),
    });
    const resolved = await fetchLatestPuzzle("nba", "2026-06-01", fetchImpl);
    expect(resolved!.date).toBe("2026-05-29");
  });

  it("returns null when there are no puzzles and no index", async () => {
    const fetchImpl = stubFetch({});
    const resolved = await fetchLatestPuzzle("nba", "2026-06-01", fetchImpl);
    expect(resolved).toBeNull();
  });
});

describe("fetchLatestBee", () => {
  it("returns today's Bee when present (isToday=true)", async () => {
    const fetchImpl = stubFetch({
      "/puzzles/nba/bee/2026-05-29.json": () => ok(NBA_BEE),
    });
    const resolved = await fetchLatestBee("nba", "2026-05-29", fetchImpl);
    expect(resolved!.isToday).toBe(true);
    expect(resolved!.date).toBe("2026-05-29");
  });

  it("falls back to the latest indexed Bee when today's is missing", async () => {
    const fetchImpl = stubFetch({
      "/puzzles/nba/bee/index.json": () =>
        ok(
          JSON.stringify({
            dates: ["2026-05-29", "2026-05-26"],
            latest: "2026-05-29",
          }),
        ),
      "/puzzles/nba/bee/2026-05-29.json": () => ok(NBA_BEE),
    });
    const resolved = await fetchLatestBee("nba", "2026-06-01", fetchImpl);
    expect(resolved!.isToday).toBe(false);
    expect(resolved!.date).toBe("2026-05-29");
  });

  it("returns null for a league with no Bees (e.g. combined)", async () => {
    const fetchImpl = stubFetch({});
    const resolved = await fetchLatestBee("combined", "2026-06-01", fetchImpl);
    expect(resolved).toBeNull();
  });
});
