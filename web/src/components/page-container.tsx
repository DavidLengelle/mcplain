import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const CONTAINER = "mx-auto w-full max-w-[1180px] px-4 sm:px-6";

export function PageContainer({ children }: { children: ReactNode }) {
  return <div className={cn(CONTAINER, "pt-8 pb-10")}>{children}</div>;
}
