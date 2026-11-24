import { readFile } from "node:fs/promises";
import { createServer } from "node:http";

const SCRIPT = new URL("../fixtures/umami-script-3.4.1.js", import.meta.url);
const BODY_LIMIT = 65536;
const port = Number(process.argv[2]);
const records = [];

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

function readBody(request) {
  return new Promise((resolve) => {
    let text = "";
    request.on("data", (chunk) => {
      text += chunk;
      if (text.length > BODY_LIMIT) {
        request.destroy();
      }
    });
    request.on("end", () => resolve(text));
  });
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
  if (url.pathname === "/health") {
    send(response, 200, { status: "ok" });
    return;
  }
  if (request.method === "GET" && url.pathname === "/script.js") {
    response.writeHead(200, { "Content-Type": "application/javascript" });
    response.end(await readFile(SCRIPT));
    return;
  }
  if (request.method === "POST" && url.pathname === "/api/send") {
    const text = await readBody(request);
    records.push({ headers: request.headers, body: JSON.parse(text) });
    send(response, 200, { cache: "fake-cache-token" });
    return;
  }
  if (request.method === "GET" && url.pathname === "/records") {
    const agent = url.searchParams.get("agent");
    send(response, 200, records.filter((record) => record.headers["user-agent"] === agent));
    return;
  }
  send(response, 404, {});
});

server.listen(port, "127.0.0.1");
