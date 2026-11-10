export type Settings = {
  databaseUrl: string;
  secret: string;
  publicUrl: string;
  apiUrl: string;
  trustedProxyHops: number;
  port: number;
};

const MIN_SECRET_LENGTH = 32;
const MAX_PROXY_HOPS = 5;
const DEFAULT_PORT = 3100;
const DEFAULT_API_URL = "http://api:8000";

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = (env[name] ?? "").trim();
  if (value === "") {
    throw new Error(`${name} is missing: run scripts/init-secrets.sh`);
  }
  return value;
}

function origin(text: string, name: string): string {
  const url = new URL(text);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new Error(`${name} must start with http:// or https://`);
  }
  return url.origin;
}

function integer(text: string | undefined, fallback: number, low: number, high: number, name: string): number {
  if (text === undefined || text.trim() === "") {
    return fallback;
  }
  const value = Number(text);
  if (!Number.isInteger(value) || value < low || value > high) {
    throw new Error(`${name} must be an integer from ${low} to ${high}`);
  }
  return value;
}

export function readSettings(env: NodeJS.ProcessEnv): Settings {
  const secret = required(env, "BETTER_AUTH_SECRET");
  if (secret.length < MIN_SECRET_LENGTH) {
    throw new Error(`BETTER_AUTH_SECRET must be at least ${MIN_SECRET_LENGTH} characters long`);
  }
  let apiUrl = env.MCPLAIN_API_INTERNAL_URL;
  if (apiUrl === undefined || apiUrl.trim() === "") {
    apiUrl = DEFAULT_API_URL;
  }
  return {
    databaseUrl: required(env, "MCPLAIN_GUICHET_DATABASE_URL"),
    secret,
    publicUrl: origin(required(env, "MCPLAIN_PUBLIC_URL"), "MCPLAIN_PUBLIC_URL"),
    apiUrl: origin(apiUrl, "MCPLAIN_API_INTERNAL_URL"),
    trustedProxyHops: integer(env.MCPLAIN_TRUSTED_PROXY_HOPS, 1, 0, MAX_PROXY_HOPS, "MCPLAIN_TRUSTED_PROXY_HOPS"),
    port: integer(env.MCPLAIN_GUICHET_PORT, DEFAULT_PORT, 1, 65535, "MCPLAIN_GUICHET_PORT"),
  };
}

export function isSecure(settings: Settings): boolean {
  return settings.publicUrl.startsWith("https://");
}
