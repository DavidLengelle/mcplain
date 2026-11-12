export const QUOTA_PATH = "/api/quota";
export const HISTORY_PATH = "/api/account/history";
export const QUOTA_KINDS = ["anonymous", "account", "admin", "bench"] as const;

export type QuotaKind = (typeof QUOTA_KINDS)[number];

export type QuotaInfo = {
  kind: QuotaKind;
  limit: number | null;
  used: number;
  remaining: number | null;
  resetsAt: string;
};

export type HistoryEntry = {
  date: string | null;
  id: string;
  input: string;
  select: string | null;
  state: string;
  color: string | null;
  status: string | null;
  fromCache: boolean;
};

type Fields = Record<string, unknown>;

function fields(value: unknown): Fields | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Fields;
}

function count(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value) && value >= 0) {
    return value;
  }
  return null;
}

function optionalString(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return null;
}

function isKind(value: unknown): value is QuotaKind {
  return typeof value === "string" && (QUOTA_KINDS as readonly string[]).includes(value);
}

export function parseQuota(value: unknown): QuotaInfo | null {
  const data = fields(value);
  if (data === null || !isKind(data.kind)) {
    return null;
  }
  const used = count(data.used);
  const resetsAt = optionalString(data.resets_at);
  if (used === null || resetsAt === null || Number.isNaN(Date.parse(resetsAt))) {
    return null;
  }
  const limit = count(data.limit);
  const remaining = count(data.remaining);
  if ((data.kind === "anonymous" || data.kind === "account") && (limit === null || remaining === null)) {
    return null;
  }
  return { kind: data.kind, limit, used, remaining, resetsAt };
}

function historyEntry(value: unknown): HistoryEntry | null {
  const data = fields(value);
  if (data === null) {
    return null;
  }
  const id = optionalString(data.id);
  const input = optionalString(data.input);
  const state = optionalString(data.state);
  if (id === null || input === null || state === null) {
    return null;
  }
  return {
    date: optionalString(data.date),
    id,
    input,
    select: optionalString(data.select),
    state,
    color: optionalString(data.color),
    status: optionalString(data.status),
    fromCache: data.from_cache === true,
  };
}

export function parseHistory(value: unknown): HistoryEntry[] | null {
  const data = fields(value);
  if (data === null || !Array.isArray(data.entries)) {
    return null;
  }
  const entries: HistoryEntry[] = [];
  for (const item of data.entries) {
    const entry = historyEntry(item);
    if (entry === null) {
      return null;
    }
    entries.push(entry);
  }
  return entries;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function fetchQuota(): Promise<QuotaInfo | null> {
  try {
    const response = await fetch(QUOTA_PATH, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return parseQuota(await readJson(response));
  } catch {
    return null;
  }
}

export async function fetchHistory(): Promise<HistoryEntry[] | null> {
  try {
    const response = await fetch(HISTORY_PATH, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    return parseHistory(await readJson(response));
  } catch {
    return null;
  }
}

export async function clearHistory(): Promise<boolean> {
  try {
    const response = await fetch(HISTORY_PATH, { method: "DELETE", headers: { Accept: "application/json" } });
    return response.ok;
  } catch {
    return false;
  }
}

export function nextMidnightUtc(now: Date): string {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
  return next.toISOString();
}
