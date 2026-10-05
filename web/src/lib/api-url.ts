export const DEFAULT_API_URL = "http://127.0.0.1:8000";

const ALLOWED_PROTOCOLS = ["http:", "https:"];

export function apiBaseUrl(value: string | undefined = process.env.MCPLAIN_API_URL): string {
  const text = (value ?? "").trim();
  if (text === "") {
    return DEFAULT_API_URL;
  }
  const url = new URL(text);
  if (!ALLOWED_PROTOCOLS.includes(url.protocol)) {
    throw new Error("MCPLAIN_API_URL must start with http:// or https://");
  }
  return url.origin;
}
