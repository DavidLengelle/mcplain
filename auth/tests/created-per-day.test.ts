import { memoryAdapter } from "better-auth/adapters/memory";
import { describe, expect, it } from "vitest";

import { createAuth } from "../src/auth.ts";
import { CREATED_PER_DAY_ROUTE, internalRoutes } from "../src/internal.ts";
import type { Settings } from "../src/settings.ts";

const SETTINGS: Settings = {
  databaseUrl: "postgres://unused",
  secret: "test only secret, never a real one, 0123456789",
  publicUrl: "http://localhost:3010",
  apiUrl: "http://api:8000",
  trustedProxyHops: 1,
  port: 3100,
  internalPeers: ["api"],
};
const NOW = new Date("2026-11-24T10:00:00.000Z");

type Row = Record<string, unknown>;

function user(index: number, createdAt: string): Row {
  return {
    id: `user-id-${index}`,
    name: "",
    email: `person${index}@example.com`,
    emailVerified: true,
    role: "user",
    createdAt: new Date(createdAt),
    updatedAt: new Date(createdAt),
  };
}

function routesWith(users: Row[]) {
  const tables = { user: users, session: [] as Row[], account: [] as Row[], verification: [] as Row[], twoFactor: [] as Row[] };
  const auth = createAuth(SETTINGS, { database: memoryAdapter(tables), guard: async () => ({ ok: true }), deposit: async () => undefined, erase: async () => true });
  const routes = internalRoutes(auth, () => NOW);
  return (search: string) => routes({ method: "GET", path: CREATED_PER_DAY_ROUTE, search: new URLSearchParams(search), cookie: undefined, body: "" });
}

describe("accounts created per day", () => {
  it("counts the accounts of each UTC day, with the days without account at zero", async () => {
    const ask = routesWith([
      user(1, "2026-11-24T00:00:00.000Z"),
      user(2, "2026-11-24T09:59:00.000Z"),
      user(3, "2026-11-23T23:59:59.999Z"),
      user(4, "2026-11-18T12:00:00.000Z"),
      user(5, "2026-11-17T23:59:59.000Z"),
      user(6, "2026-10-01T12:00:00.000Z"),
    ]);
    const answer = await ask("days=7");
    expect(answer.status).toBe(200);
    expect(answer.body).toEqual({
      days: [
        { day: "2026-11-18", count: 1 },
        { day: "2026-11-19", count: 0 },
        { day: "2026-11-20", count: 0 },
        { day: "2026-11-21", count: 0 },
        { day: "2026-11-22", count: 0 },
        { day: "2026-11-23", count: 1 },
        { day: "2026-11-24", count: 2 },
      ],
    });
    const month = await ask("days=30");
    const days = (month.body as { days: { day: string; count: number }[] }).days;
    expect(days).toHaveLength(30);
    expect(days[0]?.day).toBe("2026-10-26");
    expect(days.reduce((total, item) => total + item.count, 0)).toBe(5);
  });

  it("refuses any other number of days", async () => {
    const ask = routesWith([]);
    for (const search of ["", "days=", "days=1", "days=31", "days=365", "days=7.0", "days=abc", "days=-7"]) {
      expect((await ask(search)).status, search).toBe(400);
    }
  });

  it("gives dates and numbers only, never an address nor an identifier", async () => {
    const ask = routesWith([user(1, "2026-11-24T08:00:00.000Z"), user(2, "2026-11-20T08:00:00.000Z")]);
    const text = JSON.stringify((await ask("days=30")).body);
    expect(text).not.toContain("@");
    expect(text).not.toContain("user-id");
    expect(text).not.toContain("person");
    const body = (await ask("days=30")).body as { days: Record<string, unknown>[] };
    expect(Object.keys(body)).toEqual(["days"]);
    for (const item of body.days) {
      expect(Object.keys(item).sort()).toEqual(["count", "day"]);
      expect(item.day).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(Number.isInteger(item.count)).toBe(true);
    }
  });
});
