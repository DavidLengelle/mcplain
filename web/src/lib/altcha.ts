export const ALTCHA_CHALLENGE_URL = "/api/altcha/challenge";
export const ALTCHA_ALGORITHM = "PBKDF2/SHA-256";
export const ALTCHA_WORKER_PATH = "/altcha/pbkdf2.js";

let loading: Promise<void> | null = null;

function pbkdf2Worker(): Worker {
  return new Worker(ALTCHA_WORKER_PATH);
}

export function loadAltcha(): Promise<void> {
  if (loading === null) {
    loading = import("altcha/external").then(() => {
      globalThis.$altcha.algorithms.set(ALTCHA_ALGORITHM, pbkdf2Worker);
    });
  }
  return loading;
}
