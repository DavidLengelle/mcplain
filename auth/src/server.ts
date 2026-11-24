import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import { toNodeHandler } from "better-auth/node";
import pg from "pg";

import { createAuth, BASE_PATH } from "./auth.ts";
import { setLimiterAddress } from "./client-ip.ts";
import { apiErase } from "./erase.ts";
import { apiGuard } from "./guard.ts";
import { INTERNAL_BODY_MAX_BYTES, INTERNAL_PREFIX, internalRoutes } from "./internal.ts";
import { outboxDeposit } from "./outbox.ts";
import { PeerCheck } from "./peers.ts";
import { readSettings } from "./settings.ts";

const HEALTH_PATH = "/health";
const POOL_SIZE = 10;
const JSON_HEADERS = { "Content-Type": "application/json", "Cache-Control": "no-store" };

const settings = readSettings(process.env);
const pool = new pg.Pool({ connectionString: settings.databaseUrl, options: "-c search_path=auth", max: POOL_SIZE });
const auth = createAuth(settings, { database: pool, guard: apiGuard(settings.apiUrl), deposit: outboxDeposit(pool), erase: apiErase(settings.apiUrl) });
const handle = toNodeHandler(auth);
const internal = internalRoutes(auth);
const peers = new PeerCheck(settings.internalPeers);

function answer(response: ServerResponse, status: number, body: unknown): void {
  response.writeHead(status, JSON_HEADERS).end(JSON.stringify(body));
}

async function readBody(request: IncomingMessage): Promise<string | null> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const piece = Buffer.from(chunk as Buffer);
    size += piece.length;
    if (size > INTERNAL_BODY_MAX_BYTES) {
      return null;
    }
    chunks.push(piece);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function serveInternal(request: IncomingMessage, response: ServerResponse, path: string, search: string): Promise<void> {
  if (!(await peers.allows(request.socket.remoteAddress))) {
    answer(response, 404, { error: "not_found" });
    return;
  }
  const body = await readBody(request);
  if (body === null) {
    answer(response, 413, { error: "too_large" });
    return;
  }
  let cookie: string | undefined;
  if (typeof request.headers.cookie === "string") {
    cookie = request.headers.cookie;
  }
  try {
    const result = await internal({ method: request.method ?? "", path, search: new URLSearchParams(search), cookie, body });
    answer(response, result.status, result.body);
  } catch {
    answer(response, 503, { error: "unavailable" });
  }
}

const server = createServer((request, response) => {
  const [path = "", search = ""] = (request.url ?? "").split("?", 2);
  if (request.method === "GET" && path === HEALTH_PATH) {
    response.writeHead(200, { "Content-Type": "application/json" }).end('{"status":"ok"}');
    return;
  }
  if (path.startsWith(INTERNAL_PREFIX)) {
    void serveInternal(request, response, path, search);
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
