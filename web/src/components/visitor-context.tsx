"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { authClient } from "@/lib/auth-client";
import { fetchQuota, type QuotaInfo } from "@/lib/quota";

import { AltchaField, type AltchaHandle } from "./account/altcha-field";

export type VisitorServices = {
  quota: QuotaInfo | null;
  refreshQuota: () => void;
  solveAltcha: () => Promise<string | null>;
};

const NOBODY: VisitorServices = {
  quota: null,
  refreshQuota: () => {},
  solveAltcha: async () => null,
};

export const VisitorContext = createContext<VisitorServices>(NOBODY);

export function useVisitor(): VisitorServices {
  return useContext(VisitorContext);
}

export function VisitorProvider({ children }: { children: ReactNode }) {
  const altcha = useRef<AltchaHandle>(null);
  const session = authClient.useSession();
  const userId = session.data?.user?.id ?? null;
  const [quota, setQuota] = useState<QuotaInfo | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    void fetchQuota().then((answer) => {
      if (active) {
        setQuota(answer);
      }
    });
    return () => {
      active = false;
    };
  }, [userId, version]);

  const refreshQuota = useCallback(() => setVersion((count) => count + 1), []);
  const solveAltcha = useCallback(async () => (await altcha.current?.solve()) ?? null, []);
  const services = useMemo<VisitorServices>(
    () => ({ quota, refreshQuota, solveAltcha }),
    [quota, refreshQuota, solveAltcha],
  );

  return (
    <VisitorContext value={services}>
      <AltchaField ref={altcha} />
      {children}
    </VisitorContext>
  );
}
