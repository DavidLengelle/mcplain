import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

const LOCALES = new URL("../../../engine/src/mcplain/locales/", import.meta.url);
const LANGUAGES = new Set(["en", "fr"]);
const port = Number(process.argv[2]);

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

const server = createServer(async (request, response) => {
  const match = /^\/api\/messages\/([a-z]+)$/.exec(request.url ?? "");
  if (request.url === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }
  if (request.method !== "GET" || match === null || !LANGUAGES.has(match[1])) {
    send(response, 404, { error: { code: "api.not_found", params: {} } });
    return;
  }
  const text = await readFile(new URL(`${match[1]}.json`, LOCALES), "utf-8");
  response.writeHead(200, { "Content-Type": "application/json" });
  response.end(text);
});

server.listen(port, "127.0.0.1");
