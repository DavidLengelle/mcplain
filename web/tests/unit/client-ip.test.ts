import { createServer, type IncomingMessage } from "node:http";
import { createRequire } from "node:module";
import type { AddressInfo } from "node:net";

import { describe, expect, it } from "vitest";

type Module = { appendClientAddress: (request: { socket?: { remoteAddress?: string }; headers: Record<string, string | undefined> }) => void };

const { appendClientAddress } = createRequire(import.meta.url)("../../client-ip.js") as Module;

describe("the address our relay appends", () => {
  it("appends the real address after whatever the browser wrote", () => {
    const faked = { socket: { remoteAddress: "203.0.113.7" }, headers: { "x-forwarded-for": "6.6.6.6" } };
    appendClientAddress(faked);
    expect(faked.headers["x-forwarded-for"]).toBe("6.6.6.6, 203.0.113.7");
    const plain: { socket: { remoteAddress: string }; headers: Record<string, string | undefined> } = {
      socket: { remoteAddress: "::ffff:203.0.113.7" },
      headers: {},
    };
    appendClientAddress(plain);
    expect(plain.headers["x-forwarded-for"]).toBe("::ffff:203.0.113.7");
  });

  it("is applied to every request of a Node server once loaded", async () => {
    let seen: string | undefined;
    const server = createServer((request: IncomingMessage, response) => {
      seen = request.headers["x-forwarded-for"] as string | undefined;
      response.end();
    });
    await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
    const { port } = server.address() as AddressInfo;
    await fetch(`http://127.0.0.1:${port}/`, { headers: { "X-Forwarded-For": "6.6.6.6" } });
    await new Promise<void>((resolve) => server.close(() => resolve()));
    expect(seen).toBe("6.6.6.6, 127.0.0.1");
  });
});
