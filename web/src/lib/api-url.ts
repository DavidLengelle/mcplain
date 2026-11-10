export const DEFAULT_API_URL = "http://127.0.0.1:8000";
export const DEFAULT_GUICHET_URL = "http://127.0.0.1:3100";

const ALLOWED_PROTOCOLS = ["http:", "https:"];

function baseUrl(value: string | undefined, fallback: string, name: string): string {
  const text = (value ?? "").trim();
  if (text === "") {
    return fallback;
  }
  const url = new URL(text);
  if (!ALLOWED_PROTOCOLS.includes(url.protocol)) {
    throw new Error(`${name} must start with http:// or https://`);
  }
  return url.origin;
}

export function apiBaseUrl(value: string | undefined = process.env.MCPLAIN_API_URL): string {
  return baseUrl(value, DEFAULT_API_URL, "MCPLAIN_API_URL");
}

export function guichetBaseUrl(value: string | undefined = process.env.MCPLAIN_GUICHET_URL): string {
  return baseUrl(value, DEFAULT_GUICHET_URL, "MCPLAIN_GUICHET_URL");
}

export function relayRewrites(api: string = apiBaseUrl(), guichet: string = guichetBaseUrl()) {
  return [
    { source: "/api/auth/:path*", destination: `${guichet}/api/auth/:path*` },
    { source: "/api/:path*", destination: `${api}/api/:path*` },
  ];
}
