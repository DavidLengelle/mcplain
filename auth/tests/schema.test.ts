import { getMigrations } from "better-auth/db/migration";
import pg from "pg";
import { describe, expect, it } from "vitest";

import { authOptions } from "../src/auth.ts";

const URL_VARIABLE = "MCPLAIN_TEST_GUICHET_DATABASE_URL";
const databaseUrl = process.env[URL_VARIABLE];

describe.skipIf(!databaseUrl)("the auth schema built by Alembic", () => {
  it("is exactly what Better Auth expects: nothing to create, nothing to add", async () => {
    const pool = new pg.Pool({ connectionString: databaseUrl, options: "-c search_path=auth", max: 1 });
    try {
      const settings = {
        databaseUrl: databaseUrl ?? "",
        secret: "test only secret, never a real one, 0123456789",
        publicUrl: "http://localhost:3000",
        apiUrl: "http://api:8000",
        trustedProxyHops: 1,
        port: 3100,
      };
      const options = authOptions(settings, { database: pool, guard: async () => ({ ok: true }), deposit: async () => {} });
      const { toBeCreated, toBeAdded } = await getMigrations(options);
      expect(toBeCreated.map((table) => table.table)).toEqual([]);
      expect(toBeAdded.map((table) => table.table)).toEqual([]);
    } finally {
      await pool.end();
    }
  });
});
