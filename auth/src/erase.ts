export type Erase = (userId: string) => Promise<boolean>;

export const ERASE_UNAVAILABLE = "ERASE_UNAVAILABLE";
const ERASE_PATH = "/internal/account-erase";
const TIMEOUT_MS = 5000;

export function apiErase(apiUrl: string, fetcher: typeof fetch = fetch): Erase {
  return async (userId) => {
    try {
      const response = await fetcher(`${apiUrl}${ERASE_PATH}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId }),
        redirect: "error",
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
      return response.status === 200;
    } catch {
      return false;
    }
  };
}
