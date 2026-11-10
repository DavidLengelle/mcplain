export type GuardAction = "sign_up" | "sign_in" | "request_password_reset";

export type GuardAnswer = { ok: true } | { ok: false; code: string };

export type Guard = (action: GuardAction, altcha: string | null, ipHeaders: Record<string, string>) => Promise<GuardAnswer>;

export const GUARDED_PATHS: Record<string, GuardAction> = {
  "/sign-up/email": "sign_up",
  "/sign-in/email": "sign_in",
  "/request-password-reset": "request_password_reset",
};

export const ALTCHA_HEADER = "x-altcha";
export const FORWARDED_FOR = "x-forwarded-for";
export const GUARD_UNAVAILABLE = "guard_unavailable";
const KNOWN_REFUSALS = new Set(["altcha_invalid", "signup_limit"]);
const GUARD_PATH = "/internal/auth-guard";
const TIMEOUT_MS = 5000;
const ALTCHA_MAX_CHARS = 4096;

export function ipHeaders(headers: Headers | undefined): Record<string, string> {
  const kept: Record<string, string> = {};
  const value = headers?.get(FORWARDED_FOR);
  if (value) {
    kept[FORWARDED_FOR] = value;
  }
  return kept;
}

export function altchaPayload(headers: Headers | undefined): string | null {
  const value = headers?.get(ALTCHA_HEADER);
  if (!value || value.length > ALTCHA_MAX_CHARS) {
    return null;
  }
  return value;
}

async function refusalCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "code" in body && typeof body.code === "string") {
      if (KNOWN_REFUSALS.has(body.code)) {
        return body.code;
      }
    }
  } catch {
    return GUARD_UNAVAILABLE;
  }
  return GUARD_UNAVAILABLE;
}

export function apiGuard(apiUrl: string, fetcher: typeof fetch = fetch): Guard {
  return async (action, altcha, headers) => {
    let response: Response;
    try {
      response = await fetcher(`${apiUrl}${GUARD_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, altcha, ip_headers: headers }),
        redirect: "error",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch {
      return { ok: false, code: GUARD_UNAVAILABLE };
    }
    if (response.status === 200) {
      return { ok: true };
    }
    return { ok: false, code: await refusalCode(response) };
  };
}
