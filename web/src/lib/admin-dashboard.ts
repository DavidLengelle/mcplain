export const DAY_CHOICES = [7, 30] as const;
export type Days = (typeof DAY_CHOICES)[number];
export const DEFAULT_DAYS: Days = 30;
export const CREDIT_NOTE_MAX_CHARACTERS = 100;

const DASHBOARD_PATH = "/api/admin/dashboard";
const CREDIT_PATH = "/api/admin/credit";
const JOURNAL_PATH = "/api/admin/journal";

type Json = Record<string, unknown>;

export type Writer = { disabledReason: string | null; pausedUntil: string | null };

export type SpendDay = { day: string; costUsd: number; noticeUsd: number; translationUsd: number; paidCalls: number };
export type Spend = {
  todayUsd: number;
  monthUsd: number;
  dailyFuseUsd: number;
  monthlyBudgetUsd: number;
  fuseReached: boolean;
  budgetReached: boolean;
  perDay: SpendDay[];
  noticeUsd: number;
  translationUsd: number;
  paidCalls: number;
  writer: Writer;
};

export type Counted = { code: string; count: number };
export type Alert = { id: string; code: string; createdAt: string | null; kind: string | null; status: number | null; emailedAt: string | null; readAt: string | null };
export type AiText = { id: string; kind: string; lang: string; status: string; rejectReason: string | null; updatedAt: string | null; analysisId: string | null };
export type AiHealth = {
  perDay: { day: string; reasons: Counted[] }[];
  reasons: Counted[];
  encoding: { rejected: number; paidNoticeCalls: number; rate: number | null };
  alerts: Alert[];
  texts: AiText[];
  writer: Writer;
};

export type Failure = Counted & { refund: string };
export type TopEntry = { kind: string; name: string; count: number; lastAnalysisId: string | null };
export type Analyses = {
  perDay: { day: string; total: number; cached: number; fresh: number }[];
  colors: Counted[];
  grayCases: Counted[];
  languages: Counted[];
  failures: Failure[];
  top: TopEntry[];
};

export type Refusals = { kinds: string[]; perDay: { day: string; counts: Counted[] }[]; totals: Counted[] };
export type Accounts = { perDay: { day: string; count: number }[]; total: number };

export type CreditEntry = { id: string; kind: string; amountUsd: number; note: string | null; createdAt: string | null };
export type Credit = {
  balanceUsd: number | null;
  statementUsd: number | null;
  statementAt: string | null;
  topUpsUsd: number;
  spentUsd: number;
  thresholdUsd: number;
  low: boolean;
  alertSentAt: string | null;
  lastEntryId: string | null;
  entries: CreditEntry[];
};

export type JournalLine = { id: string; action: string; targetKind: string; targetId: string; createdAt: string | null };

export type Read<T> = { kind: "ready"; value: T } | { kind: "unavailable" } | { kind: "refused" } | { kind: "failed" };

export type ActionOutcome = { kind: "done" } | { kind: "refused"; code: string } | { kind: "failed" };

function record(value: unknown): Json | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Json;
  }
  return null;
}

function list(value: unknown): unknown[] {
  if (Array.isArray(value)) {
    return value;
  }
  return [];
}

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return null;
}

function number(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  return null;
}

function amount(value: unknown): number {
  return number(value) ?? 0;
}

function counted(value: unknown): Counted[] {
  const items: Counted[] = [];
  for (const item of list(value)) {
    const entry = record(item);
    const code = text(entry?.code);
    const count = number(entry?.count);
    if (code !== null && count !== null) {
      items.push({ code, count });
    }
  }
  return items;
}

function countedMap(value: unknown): Counted[] {
  const entry = record(value);
  if (entry === null) {
    return [];
  }
  const items: Counted[] = [];
  for (const [code, count] of Object.entries(entry)) {
    const parsed = number(count);
    if (parsed !== null) {
      items.push({ code, count: parsed });
    }
  }
  return items;
}

function writerOf(value: unknown): Writer {
  const entry = record(value);
  return { disabledReason: text(entry?.disabled_reason), pausedUntil: text(entry?.paused_until) };
}

export function parseSpend(value: unknown): Spend | null {
  const body = record(value);
  if (body === null || number(body.today_usd) === null || number(body.month_usd) === null) {
    return null;
  }
  const byKind = record(body.by_kind);
  const perDay: SpendDay[] = [];
  for (const item of list(body.per_day)) {
    const entry = record(item);
    const day = text(entry?.day);
    if (entry === null || day === null) {
      continue;
    }
    perDay.push({
      day,
      costUsd: amount(entry.cost_usd),
      noticeUsd: amount(entry.notice_usd),
      translationUsd: amount(entry.translation_usd),
      paidCalls: amount(entry.paid_calls),
    });
  }
  return {
    todayUsd: amount(body.today_usd),
    monthUsd: amount(body.month_usd),
    dailyFuseUsd: amount(body.daily_fuse_usd),
    monthlyBudgetUsd: amount(body.monthly_budget_usd),
    fuseReached: body.fuse_reached === true,
    budgetReached: body.budget_reached === true,
    perDay,
    noticeUsd: amount(byKind?.notice),
    translationUsd: amount(byKind?.translation),
    paidCalls: amount(body.paid_calls),
    writer: writerOf(body.writer),
  };
}

export function parseAiHealth(value: unknown): AiHealth | null {
  const body = record(value);
  const encoding = record(body?.encoding);
  if (body === null || encoding === null) {
    return null;
  }
  const alerts: Alert[] = [];
  for (const item of list(body.alerts)) {
    const entry = record(item);
    const id = text(entry?.id);
    const code = text(entry?.code);
    if (entry === null || id === null || code === null) {
      continue;
    }
    alerts.push({
      id,
      code,
      createdAt: text(entry.created_at),
      kind: text(entry.kind),
      status: number(entry.status),
      emailedAt: text(entry.emailed_at),
      readAt: text(entry.read_at),
    });
  }
  const texts: AiText[] = [];
  for (const item of list(body.texts)) {
    const entry = record(item);
    const id = text(entry?.id);
    const kind = text(entry?.kind);
    const status = text(entry?.status);
    if (entry === null || id === null || kind === null || status === null) {
      continue;
    }
    texts.push({
      id,
      kind,
      lang: text(entry.lang) ?? "",
      status,
      rejectReason: text(entry.reject_reason),
      updatedAt: text(entry.updated_at),
      analysisId: text(entry.analysis_id),
    });
  }
  const perDay: AiHealth["perDay"] = [];
  for (const item of list(body.per_day)) {
    const entry = record(item);
    const day = text(entry?.day);
    if (day !== null) {
      perDay.push({ day, reasons: countedMap(entry?.reasons) });
    }
  }
  return {
    perDay,
    reasons: countedMap(body.reasons),
    encoding: { rejected: amount(encoding.rejected), paidNoticeCalls: amount(encoding.paid_notice_calls), rate: number(encoding.rate) },
    alerts,
    texts,
    writer: writerOf(body.writer),
  };
}

export function parseAnalyses(value: unknown): Analyses | null {
  const body = record(value);
  if (body === null || record(body.colors) === null) {
    return null;
  }
  const perDay: Analyses["perDay"] = [];
  for (const item of list(body.per_day)) {
    const entry = record(item);
    const day = text(entry?.day);
    if (entry === null || day === null) {
      continue;
    }
    perDay.push({ day, total: amount(entry.total), cached: amount(entry.cached), fresh: amount(entry.new) });
  }
  const failures: Failure[] = [];
  for (const item of list(body.failures)) {
    const entry = record(item);
    const code = text(entry?.code);
    const count = number(entry?.count);
    if (code !== null && count !== null) {
      failures.push({ code, count, refund: text(entry?.refund) ?? "" });
    }
  }
  const top: TopEntry[] = [];
  for (const item of list(body.top)) {
    const entry = record(item);
    const kind = text(entry?.kind);
    const name = text(entry?.name);
    const count = number(entry?.count);
    if (kind !== null && name !== null && count !== null) {
      top.push({ kind, name, count, lastAnalysisId: text(entry?.last_analysis_id) });
    }
  }
  return {
    perDay,
    colors: countedMap(body.colors),
    grayCases: counted(body.gray_cases),
    languages: counted(body.languages),
    failures,
    top,
  };
}

export function parseRefusals(value: unknown): Refusals | null {
  const body = record(value);
  if (body === null) {
    return null;
  }
  const kinds: string[] = [];
  for (const item of list(body.kinds)) {
    const kind = text(item);
    if (kind !== null) {
      kinds.push(kind);
    }
  }
  const perDay: Refusals["perDay"] = [];
  for (const item of list(body.per_day)) {
    const entry = record(item);
    const day = text(entry?.day);
    if (day !== null) {
      perDay.push({ day, counts: countedMap(entry?.counts) });
    }
  }
  return { kinds, perDay, totals: countedMap(body.totals) };
}

export function parseAccounts(value: unknown): Accounts | null {
  const body = record(value);
  if (body === null) {
    return null;
  }
  const perDay: Accounts["perDay"] = [];
  for (const item of list(body.per_day)) {
    const entry = record(item);
    const day = text(entry?.day);
    const count = number(entry?.count);
    if (day !== null && count !== null) {
      perDay.push({ day, count });
    }
  }
  return { perDay, total: amount(body.total) };
}

export function parseCredit(value: unknown): Credit | null {
  const body = record(value);
  if (body === null || number(body.threshold_usd) === null) {
    return null;
  }
  const entries: CreditEntry[] = [];
  for (const item of list(body.entries)) {
    const entry = record(item);
    const id = text(entry?.id);
    const kind = text(entry?.kind);
    const amountUsd = number(entry?.amount_usd);
    if (entry === null || id === null || kind === null || amountUsd === null) {
      continue;
    }
    entries.push({ id, kind, amountUsd, note: text(entry.note), createdAt: text(entry.created_at) });
  }
  return {
    balanceUsd: number(body.balance_usd),
    statementUsd: number(body.statement_usd),
    statementAt: text(body.statement_at),
    topUpsUsd: amount(body.top_ups_usd),
    spentUsd: amount(body.spent_usd),
    thresholdUsd: amount(body.threshold_usd),
    low: body.low === true,
    alertSentAt: text(body.alert_sent_at),
    lastEntryId: text(body.last_entry_id),
    entries,
  };
}

export function parseJournal(value: unknown): JournalLine[] | null {
  const body = record(value);
  if (body === null || !Array.isArray(body.lines)) {
    return null;
  }
  const lines: JournalLine[] = [];
  for (const item of body.lines) {
    const entry = record(item);
    const id = text(entry?.id);
    const action = text(entry?.action);
    const targetKind = text(entry?.target_kind);
    const targetId = text(entry?.target_id);
    if (id !== null && action !== null && targetKind !== null && targetId !== null) {
      lines.push({ id, action, targetKind, targetId, createdAt: text(entry?.created_at) });
    }
  }
  return lines;
}

async function errorCode(response: Response): Promise<string> {
  try {
    const body = record(await response.json());
    const error = record(body?.error);
    return text(error?.code) ?? "";
  } catch {
    return "";
  }
}

async function readJson<T>(path: string, parse: (value: unknown) => T | null): Promise<Read<T>> {
  try {
    const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (response.status === 403) {
      return { kind: "refused" };
    }
    if (response.status === 503) {
      return { kind: "unavailable" };
    }
    if (!response.ok) {
      return { kind: "failed" };
    }
    const value = parse(await response.json());
    if (value === null) {
      return { kind: "failed" };
    }
    return { kind: "ready", value };
  } catch {
    return { kind: "failed" };
  }
}

export type DialName = "spend" | "ai" | "analyses" | "refusals" | "accounts";

function dialPath(name: DialName, days: Days): string {
  return `${DASHBOARD_PATH}/${name}?${new URLSearchParams({ days: String(days) }).toString()}`;
}

export function readSpend(days: Days): Promise<Read<Spend>> {
  return readJson(dialPath("spend", days), parseSpend);
}

export function readAiHealth(days: Days): Promise<Read<AiHealth>> {
  return readJson(dialPath("ai", days), parseAiHealth);
}

export function readAnalyses(days: Days): Promise<Read<Analyses>> {
  return readJson(dialPath("analyses", days), parseAnalyses);
}

export function readRefusals(days: Days): Promise<Read<Refusals>> {
  return readJson(dialPath("refusals", days), parseRefusals);
}

export function readAccounts(days: Days): Promise<Read<Accounts>> {
  return readJson(dialPath("accounts", days), parseAccounts);
}

export function readCredit(): Promise<Read<Credit>> {
  return readJson(CREDIT_PATH, parseCredit);
}

export function readJournal(): Promise<Read<JournalLine[]>> {
  return readJson(JOURNAL_PATH, parseJournal);
}

async function send(path: string, method: "POST" | "DELETE", body: unknown): Promise<ActionOutcome> {
  try {
    const init: RequestInit = { method, headers: { Accept: "application/json" }, cache: "no-store" };
    if (method === "POST") {
      init.headers = { Accept: "application/json", "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    const response = await fetch(path, init);
    if (response.ok) {
      return { kind: "done" };
    }
    const code = await errorCode(response);
    if (code === "") {
      return { kind: "failed" };
    }
    return { kind: "refused", code };
  } catch {
    return { kind: "failed" };
  }
}

export function addCreditEntry(kind: "statement" | "top_up", amountUsd: number, note: string): Promise<ActionOutcome> {
  let sent: string | null = note.trim();
  if (sent === "") {
    sent = null;
  }
  return send(CREDIT_PATH, "POST", { kind, amount_usd: amountUsd, note: sent });
}

export function deleteCreditEntry(id: string): Promise<ActionOutcome> {
  return send(`${CREDIT_PATH}/${encodeURIComponent(id)}`, "DELETE", null);
}

export function retryText(id: string): Promise<ActionOutcome> {
  return send(`/api/admin/texts/${encodeURIComponent(id)}/retry`, "POST", {});
}

export function rerunAnalysis(id: string): Promise<ActionOutcome> {
  return send(`/api/admin/analyses/${encodeURIComponent(id)}/rerun`, "POST", {});
}

export function markAlertRead(id: string): Promise<ActionOutcome> {
  return send(`/api/admin/alerts/${encodeURIComponent(id)}/read`, "POST", {});
}

export function parseAmount(typed: string): number | null {
  const cleaned = typed.trim().replace(",", ".");
  if (!/^\d{1,6}(\.\d{1,6})?$/.test(cleaned)) {
    return null;
  }
  return Number(cleaned);
}

export function share(value: number, max: number): number {
  if (max <= 0 || value <= 0) {
    return 0;
  }
  return Math.min(1, value / max);
}
