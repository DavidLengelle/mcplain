import type { IncomingHttpHeaders } from "node:http";

const TRUST_DEVICE_SUFFIX = ".trust_device";

export function withoutTrustDevice(cookie: string): string {
  return cookie
    .split(";")
    .map((item) => item.trim())
    .filter((item) => item !== "")
    .filter((item) => !(item.split("=", 1)[0] ?? "").trim().endsWith(TRUST_DEVICE_SUFFIX))
    .join("; ");
}

export function dropTrustDevice(headers: IncomingHttpHeaders): void {
  const cookie = headers.cookie;
  if (typeof cookie !== "string") {
    return;
  }
  const kept = withoutTrustDevice(cookie);
  if (kept === "") {
    delete headers.cookie;
    return;
  }
  headers.cookie = kept;
}
