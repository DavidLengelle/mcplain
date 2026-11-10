import { createServer } from "node:http";

import { toNodeHandler } from "better-auth/node";
import pg from "pg";

import { createAuth, BASE_PATH } from "./auth.ts";
import { setLimiterAddress } from "./client-ip.ts";
import { apiGuard } from "./guard.ts";
import { outboxDeposit } from "./outbox.ts";
import { readSettings } from "./settings.ts";

const HEALTH_PATH = "/health";
const POOL_SIZE = 10;

const settings = readSettings(process.env);
const pool = new pg.Pool({ connectionString: settings.databaseUrl, options: "-c search_path=auth", max: POOL_SIZE });
const auth = createAuth(settings, { database: pool, guard: apiGuard(settings.apiUrl), deposit: outboxDeposit(pool) });
const handle = toNodeHandler(auth);

const server = createServer((request, response) => {
  const path = (request.url ?? "").split("?")[0] ?? "";
  if (request.method === "GET" && path === HEALTH_PATH) {
    response.writeHead(200, { "Content-Type": "application/json" }).end('{"status":"ok"}');
    return;
  }
  if (!path.startsWith(`${BASE_PATH}/`)) {
    response.writeHead(404, { "Content-Type": "application/json" }).end('{"error":"not_found"}');
    return;
  }
  setLimiterAddress(request.headers, settings.trustedProxyHops);
  void handle(request, response);
});

server.listen(settings.port, "0.0.0.0", () => {
  console.log(`guichet: listening on port ${settings.port}`);
});

function stop(): void {
  server.close(() => {
    void pool.end();
  });
}

process.on("SIGTERM", stop);
process.on("SIGINT", stop);
