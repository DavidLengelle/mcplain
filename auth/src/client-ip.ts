import type { IncomingHttpHeaders } from "node:http";

export const LIMITER_IP_HEADER = "x-mcplain-limiter-ip";
const MAX_ENTRIES = 32;

function forwardedEntries(value: string | string[] | undefined): string[] {
  let values: string[] = [];
  if (typeof value === "string") {
    values = [value];
  } else if (Array.isArray(value)) {
    values = value;
  }
  return values.flatMap((item) => item.split(",")).map((item) => item.trim()).filter((item) => item !== "");
}

export function limiterAddress(headers: IncomingHttpHeaders, hops: number): string | null {
  const entries = forwardedEntries(headers["x-forwarded-for"]);
  if (hops === 0 || entries.length < hops || entries.length > MAX_ENTRIES) {
    return null;
  }
  return entries[entries.length - hops] ?? null;
}

export function setLimiterAddress(headers: IncomingHttpHeaders, hops: number): void {
  delete headers[LIMITER_IP_HEADER];
  const address = limiterAddress(headers, hops);
  if (address !== null) {
    headers[LIMITER_IP_HEADER] = address;
  }
}
