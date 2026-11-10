"use client";

import { useState } from "react";

import { authErrorKey, type AuthError, type AuthErrorKey } from "@/lib/auth-errors";

export type Outcome = { error: AuthError };

export function useAuthAction() {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<AuthErrorKey | null>(null);

  async function run(action: () => Promise<Outcome | null>): Promise<boolean> {
    setPending(true);
    setError(null);
    try {
      const outcome = await action();
      if (outcome === null) {
        return false;
      }
      if (outcome.error) {
        setError(authErrorKey(outcome.error));
        return false;
      }
      return true;
    } catch {
      setError("unavailable");
      return false;
    } finally {
      setPending(false);
    }
  }

  return { pending, error, setError, run };
}
