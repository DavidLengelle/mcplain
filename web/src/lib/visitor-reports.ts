import { ALTCHA_HEADER, ANALYSES_PATH } from "./api-client";

export const REPORT_KINDS = ["false_alarm", "missed_danger", "author_error"] as const;
export type ReportKind = (typeof REPORT_KINDS)[number];
export const REPORT_STATUSES = ["new", "handled", "rejected"] as const;
export type ReportStatus = (typeof REPORT_STATUSES)[number];
export const COMMENT_MAX_CHARACTERS = 500;

const ADMIN_REPORTS_PATH = "/api/admin/reports";

export type SendOutcome =
  | { kind: "sent" }
  | { kind: "duplicate" }
  | { kind: "limit"; resetsAt: string | null }
  | { kind: "full" }
  | { kind: "altcha" }
  | { kind: "blocked" }
  | { kind: "too_long" }
  | { kind: "unavailable" };

export type VisitorReport = {
  id: string;
  analysisId: string | null;
  kind: string;
  unverified: boolean;
  status: string;
  comment: string | null;
  engineVersion: string | null;
  rulesVersion: string | null;
  color: string | null;
  reporterKind: string;
  accountId: string | null;
  createdAt: string | null;
  closedAt: string | null;
  commentErasedAt: string | null;
};

export type ReportList = { reports: VisitorReport[]; newCount: number };

export type ListRead = { kind: "ready"; value: ReportList } | { kind: "refused" } | { kind: "failed" };

type Json = Record<string, unknown>;

function record(value: unknown): Json | null {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return value as Json;
  }
  return null;
}

function text(value: unknown): string | null {
  if (typeof value === "string") {
    return value;
  }
  return null;
}

export function characterCount(value: string): number {
  return [...value].length;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function errorOf(value: unknown): { code: string; resetsAt: string | null } | null {
  const error = record(record(value)?.error);
  const code = text(error?.code);
  if (code === null) {
    return null;
  }
  return { code, resetsAt: text(record(error?.params)?.resets_at) };
}

export function outcomeOf(status: number, value: unknown): SendOutcome {
  if (status === 201) {
    return { kind: "sent" };
  }
  const error = errorOf(value);
  if (error === null) {
    return { kind: "unavailable" };
  }
  if (error.code === "report_duplicate") {
    return { kind: "duplicate" };
  }
  if (error.code === "report_limit") {
    return { kind: "limit", resetsAt: error.resetsAt };
  }
  if (error.code === "report_global") {
    return { kind: "full" };
  }
  if (error.code === "altcha_invalid") {
    return { kind: "altcha" };
  }
  if (error.code === "api.account_blocked") {
    return { kind: "blocked" };
  }
  if (error.code === "api.comment_too_long") {
    return { kind: "too_long" };
  }
  return { kind: "unavailable" };
}

export async function sendReport(analysisId: string, kind: ReportKind, comment: string, altcha: string): Promise<SendOutcome> {
  const body: { kind: ReportKind; comment?: string } = { kind };
  if (comment.trim() !== "") {
    body.comment = comment;
  }
  try {
    const response = await fetch(`${ANALYSES_PATH}/${encodeURIComponent(analysisId)}/reports`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json", [ALTCHA_HEADER]: altcha },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    return outcomeOf(response.status, await readJson(response));
  } catch {
    return { kind: "unavailable" };
  }
}

function reportOf(value: unknown): VisitorReport | null {
  const entry = record(value);
  const id = text(entry?.id);
  const kind = text(entry?.kind);
  const status = text(entry?.status);
  const reporterKind = text(entry?.reporter_kind);
  if (entry === null || id === null || kind === null || status === null || reporterKind === null) {
    return null;
  }
  return {
    id,
    analysisId: text(entry.analysis_id),
    kind,
    unverified: entry.unverified === true,
    status,
    comment: text(entry.comment),
    engineVersion: text(entry.engine_version),
    rulesVersion: text(entry.rules_version),
    color: text(entry.color),
    reporterKind,
    accountId: text(entry.account_id),
    createdAt: text(entry.created_at),
    closedAt: text(entry.closed_at),
    commentErasedAt: text(entry.comment_erased_at),
  };
}

export function parseReportList(value: unknown): ReportList | null {
  const body = record(value);
  if (body === null || !Array.isArray(body.reports) || typeof body.new_count !== "number") {
    return null;
  }
  const reports: VisitorReport[] = [];
  for (const item of body.reports) {
    const report = reportOf(item);
    if (report !== null) {
      reports.push(report);
    }
  }
  return { reports, newCount: body.new_count };
}

export async function readReportList(status: ReportStatus | null, kind: ReportKind | null): Promise<ListRead> {
  const query = new URLSearchParams();
  if (status !== null) {
    query.set("status", status);
  }
  if (kind !== null) {
    query.set("kind", kind);
  }
  let path = ADMIN_REPORTS_PATH;
  if (query.size > 0) {
    path = `${path}?${query.toString()}`;
  }
  try {
    const response = await fetch(path, { headers: { Accept: "application/json" }, cache: "no-store" });
    if (response.status === 403) {
      return { kind: "refused" };
    }
    if (!response.ok) {
      return { kind: "failed" };
    }
    const value = parseReportList(await readJson(response));
    if (value === null) {
      return { kind: "failed" };
    }
    return { kind: "ready", value };
  } catch {
    return { kind: "failed" };
  }
}

export async function changeReportStatus(id: string, status: "handled" | "rejected"): Promise<boolean> {
  try {
    const response = await fetch(`${ADMIN_REPORTS_PATH}/${encodeURIComponent(id)}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ status }),
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}
