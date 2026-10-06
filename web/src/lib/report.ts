import type { Alert, AnalysisResult, Finding, Lamp, Server, Tool, VerdictColor } from "./analysis";

export const SERVER_CODE = "server_code";
export const MAX_CANDIDATES = 50;
export const MAX_PLACES = 6;

export type ColoredVerdict = Exclude<VerdictColor, "gray">;

export const GAUGE_ANGLES: Record<ColoredVerdict, number> = { green: -60, orange: 0, red: 60 };

export type LampCount = { lit: number; danger: number; total: number };

export type Place = { function: string | null; file: string; line: number | null };

export type InvisibleCount = { label: string; count: number };

export function litLamps(lamps: Lamp[]): Lamp[] {
  return lamps.filter((lamp) => lamp.state !== "off");
}

export function countLamps(lamps: Lamp[]): LampCount {
  const lit = litLamps(lamps);
  return { lit: lit.length, danger: lit.filter((lamp) => lamp.state === "danger").length, total: lamps.length };
}

export function alertsOfColor(alerts: Alert[], color: "red" | "orange"): Alert[] {
  return alerts.filter((alert) => alert.color === color);
}

export function toolIndexOf(tools: Tool[], name: string | null): number | null {
  if (name === null) {
    return null;
  }
  const index = tools.findIndex((tool) => tool.name === name);
  if (index < 0) {
    return null;
  }
  return index;
}

export function defaultToolIndex(tools: Tool[], alerts: Alert[]): number {
  for (const alert of alerts) {
    const index = toolIndexOf(tools, alert.tool);
    if (index !== null) {
      return index;
    }
  }
  for (const level of ["danger", "warn"] as const) {
    const index = tools.findIndex((tool) => tool.level === level);
    if (index >= 0) {
      return index;
    }
  }
  return 0;
}

export function alertsOfTool(tool: Tool, alerts: Alert[]): Alert[] {
  return alerts.filter((alert) => alert.tool !== null && alert.tool === tool.name);
}

export function placeText(place: Place): string {
  let where = place.file;
  if (place.line !== null) {
    where = `${place.file}:${place.line}`;
  }
  if (place.function === null || place.function === "") {
    return where;
  }
  return `${place.function}() · ${where}`;
}

export function alertPlace(alert: Alert): string | null {
  if (alert.file === null) {
    return null;
  }
  return placeText({ function: alert.function, file: alert.file, line: alert.line });
}

function countedFindings(findings: Finding[]): Finding[] {
  return findings.filter((finding) => finding.location_kind === SERVER_CODE);
}

export function findingPlaces(tool: Tool, limit: number = MAX_PLACES): { places: string[]; more: number } {
  const places: string[] = [];
  for (const finding of countedFindings(tool.findings)) {
    const text = placeText({ function: finding.function, file: finding.file, line: finding.line });
    if (!places.includes(text)) {
      places.push(text);
    }
  }
  return { places: places.slice(0, limit), more: Math.max(0, places.length - limit) };
}

export function codeDomains(server: Server): string[] {
  const domains = server.domains.filter((ref) => ref.location_kind === SERVER_CODE).map((ref) => ref.domain);
  return Array.from(new Set(domains)).sort();
}

export function sensitiveMatches(server: Server): string[] {
  const matches = server.sensitive_paths.filter((ref) => ref.location_kind === SERVER_CODE).map((ref) => ref.match);
  return Array.from(new Set(matches));
}

export function invisibleCounts(server: Server): InvisibleCount[] {
  const counts = new Map<string, number>();
  for (const item of server.invisible_unicode) {
    if (item.location_kind !== SERVER_CODE) {
      continue;
    }
    for (const label of item.codepoints) {
      counts.set(label, (counts.get(label) ?? 0) + 1);
    }
  }
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((first, second) => first.label.localeCompare(second.label));
}

export function alertsOutsideTools(alerts: Alert[], tools: Tool[]): Alert[] {
  return alerts.filter((alert) => toolIndexOf(tools, alert.tool) === null);
}

export function firstServer(result: AnalysisResult): Server | null {
  if (result.servers.length === 0) {
    return null;
  }
  return result.servers[0];
}

export function joinList(locale: string, items: string[]): string {
  return new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(items);
}

export function toolNumber(index: number): string {
  return String(index + 1).padStart(2, "0");
}

export function isColored(color: VerdictColor): color is ColoredVerdict {
  return color !== "gray";
}
