export const VERDICT_COLORS = ["red", "orange", "green", "gray"] as const;
export const ANALYSIS_STATES = ["queued", "fetching", "analyzing", "done", "failed"] as const;
export const RUNNING_STATES = ["queued", "fetching", "analyzing"] as const;
export const ANALYSIS_STATUSES = [
  "ok",
  "multiple_servers",
  "unsupported_language",
  "compiled",
  "not_a_server",
  "error",
] as const;
export const OUTSIDE_KINDS = ["startup", "install", "never_called"] as const;
export const MESSAGE_KEY_PATTERN = /^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$/;

export type VerdictColor = (typeof VERDICT_COLORS)[number];
export type AnalysisState = (typeof ANALYSIS_STATES)[number];
export type RunningState = (typeof RUNNING_STATES)[number];
export type AnalysisStatus = (typeof ANALYSIS_STATUSES)[number];
export type OutsideKind = (typeof OUTSIDE_KINDS)[number];

export type CallStep = { function: string; file: string; line: number };

export type FlowPoint = { file: string; line: number; function: string | null; snippet: string };

export type Alert = {
  rule: string;
  color: VerdictColor;
  kind: string;
  tool: string | null;
  shared_by_tools: boolean;
  outside: OutsideKind | null;
  file: string | null;
  line: number | null;
  function: string | null;
  source: FlowPoint | null;
  steps: CallStep[];
  quote: string | null;
  detail: string | null;
};

export type Verdict = {
  color: VerdictColor;
  alerts: Alert[];
  reasons: string[];
  rules_version: string;
  rules_count: number;
  contacted_domains: string[];
};

export type Finding = {
  capability: string;
  file: string;
  line: number;
  function: string | null;
  snippet: string;
  location_kind: string;
  call_chain: CallStep[];
  shared_by_tools: boolean;
  outside: OutsideKind | null;
  url_kind: string | null;
};

export type ToolParameter = { name: string; description: string | null };

export type Tool = {
  name: string;
  name_is_dynamic: boolean;
  description: string;
  description_is_dynamic: boolean;
  title: string | null;
  title_is_dynamic: boolean;
  annotations: Record<string, boolean | "computed">;
  annotations_are_dynamic: boolean;
  parameters: ToolParameter[];
  file: string;
  line: number;
  location_kind: string;
  findings: Finding[];
  gaps: string[];
};

export type DomainRef = {
  domain: string;
  url: string;
  file: string;
  line: number;
  location_kind: string;
  tool: string | null;
};

export type SensitivePathRef = {
  category: string;
  kinds: string[];
  match: string;
  file: string;
  line: number;
  location_kind: string;
  tool: string | null;
};

export type InstallScript = { kind: string; file: string; line: number; command: string };

export type InvisibleUnicode = {
  file: string;
  line: number;
  column: number;
  category: string;
  codepoints: string[];
  hidden_text: string | null;
  in_description: boolean;
  tool: string | null;
  location_kind: string;
};

export type Server = {
  path: string;
  name: string | null;
  language: string;
  sdk: string | null;
  tools: Tool[];
  findings: Finding[];
  domains: DomainRef[];
  sensitive_paths: SensitivePathRef[];
  install_scripts: InstallScript[];
  invisible_unicode: InvisibleUnicode[];
  compiled_files: string[];
  files_analyzed: number;
};

export type Source = {
  kind: string;
  name: string;
  version: string | null;
  requested_version: string | null;
  revision: string | null;
  reference: string | null;
  subdir: string | null;
  integrity: string | null;
  url: string;
  artifact: string;
  origin: string;
  reason: string;
  repository: string | null;
};

export type MaliciousReport = { id: string; all_versions: boolean };

export type PackageReputation = {
  name: string;
  ecosystem: string;
  version: string | null;
  dependency: boolean;
  malicious: MaliciousReport[];
};

export type Reputation = { status: string; queried: number; packages: PackageReputation[] };

export type ServerCandidate = { path: string; language: string; name: string | null };

export type ErrorInfo = { code: string; params: Record<string, string> };

export type AnalysisResult = {
  status: AnalysisStatus;
  source: Source | null;
  reputation: Reputation | null;
  ignored_arguments: string[];
  servers: Server[];
  available_servers: ServerCandidate[];
  available_servers_truncated: boolean;
  language: string | null;
  compiled_files: string[];
  notes: string[];
  error: ErrorInfo | null;
  verdict: Verdict;
};

export type AnalysisView = {
  id: string;
  input: string;
  select: string | null;
  state: AnalysisState;
  created_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  result: AnalysisResult | null;
};

class InvalidResponse extends Error {}

type Fields = Record<string, unknown>;

function fail(): never {
  throw new InvalidResponse("the API answered with an unexpected shape");
}

function object(value: unknown): Fields {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    fail();
  }
  return value as Fields;
}

function text(value: unknown): string {
  if (typeof value !== "string") {
    fail();
  }
  return value;
}

function optionalText(value: unknown): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  return text(value);
}

function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    fail();
  }
  return value;
}

function optionalInteger(value: unknown): number | null {
  if (value === null || value === undefined) {
    return null;
  }
  return integer(value);
}

function flag(value: unknown): boolean {
  if (value === undefined) {
    return false;
  }
  if (typeof value !== "boolean") {
    fail();
  }
  return value;
}

function list<T>(value: unknown, item: (entry: unknown) => T): T[] {
  if (value === undefined || value === null) {
    return [];
  }
  if (!Array.isArray(value)) {
    fail();
  }
  return value.map(item);
}

function oneOf<T extends string>(value: unknown, allowed: readonly T[]): T {
  const candidate = text(value);
  if (!(allowed as readonly string[]).includes(candidate)) {
    fail();
  }
  return candidate as T;
}

function optionalOneOf<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  if (value === null || value === undefined) {
    return null;
  }
  return oneOf(value, allowed);
}

function messageKey(value: unknown): string {
  const key = text(value);
  if (!MESSAGE_KEY_PATTERN.test(key)) {
    fail();
  }
  return key;
}

function textMap(value: unknown): Record<string, string> {
  if (value === undefined || value === null) {
    return {};
  }
  const fields = object(value);
  const map: Record<string, string> = {};
  for (const [key, entry] of Object.entries(fields)) {
    map[key] = text(entry);
  }
  return map;
}

function callStep(value: unknown): CallStep {
  const fields = object(value);
  return { function: text(fields.function), file: text(fields.file), line: integer(fields.line) };
}

function flowPoint(value: unknown): FlowPoint | null {
  if (value === null || value === undefined) {
    return null;
  }
  const fields = object(value);
  return {
    file: text(fields.file),
    line: integer(fields.line),
    function: optionalText(fields.function),
    snippet: optionalText(fields.snippet) ?? "",
  };
}

function alert(value: unknown): Alert {
  const fields = object(value);
  return {
    rule: messageKey(fields.rule),
    color: oneOf(fields.color, VERDICT_COLORS),
    kind: messageKey(fields.kind),
    tool: optionalText(fields.tool),
    shared_by_tools: flag(fields.shared_by_tools),
    outside: optionalOneOf(fields.outside, OUTSIDE_KINDS),
    file: optionalText(fields.file),
    line: optionalInteger(fields.line),
    function: optionalText(fields.function),
    source: flowPoint(fields.source),
    steps: list(fields.steps, callStep),
    quote: optionalText(fields.quote),
    detail: optionalText(fields.detail),
  };
}

function verdict(value: unknown): Verdict {
  const fields = object(value);
  return {
    color: oneOf(fields.color, VERDICT_COLORS),
    alerts: list(fields.alerts, alert),
    reasons: list(fields.reasons, messageKey),
    rules_version: optionalText(fields.rules_version) ?? "",
    rules_count: optionalInteger(fields.rules_count) ?? 0,
    contacted_domains: list(fields.contacted_domains, text),
  };
}

function finding(value: unknown): Finding {
  const fields = object(value);
  return {
    capability: messageKey(fields.capability),
    file: text(fields.file),
    line: integer(fields.line),
    function: optionalText(fields.function),
    snippet: optionalText(fields.snippet) ?? "",
    location_kind: messageKey(fields.location_kind),
    call_chain: list(fields.call_chain, callStep),
    shared_by_tools: flag(fields.shared_by_tools),
    outside: optionalOneOf(fields.outside, OUTSIDE_KINDS),
    url_kind: optionalText(fields.url_kind),
  };
}

function annotations(value: unknown): Record<string, boolean | "computed"> {
  if (value === undefined || value === null) {
    return {};
  }
  const result: Record<string, boolean | "computed"> = {};
  for (const [key, entry] of Object.entries(object(value))) {
    if (typeof entry === "boolean" || entry === "computed") {
      result[messageKey(key)] = entry;
    } else {
      fail();
    }
  }
  return result;
}

function parameter(value: unknown): ToolParameter {
  const fields = object(value);
  return { name: text(fields.name), description: optionalText(fields.description) };
}

function tool(value: unknown): Tool {
  const fields = object(value);
  return {
    name: text(fields.name),
    name_is_dynamic: flag(fields.name_is_dynamic),
    description: optionalText(fields.description) ?? "",
    description_is_dynamic: flag(fields.description_is_dynamic),
    title: optionalText(fields.title),
    title_is_dynamic: flag(fields.title_is_dynamic),
    annotations: annotations(fields.annotations),
    annotations_are_dynamic: flag(fields.annotations_are_dynamic),
    parameters: list(fields.parameters, parameter),
    file: text(fields.file),
    line: integer(fields.line),
    location_kind: messageKey(fields.location_kind),
    findings: list(fields.findings, finding),
    gaps: list(fields.gaps, messageKey),
  };
}

function domainRef(value: unknown): DomainRef {
  const fields = object(value);
  return {
    domain: text(fields.domain),
    url: text(fields.url),
    file: text(fields.file),
    line: integer(fields.line),
    location_kind: messageKey(fields.location_kind),
    tool: optionalText(fields.tool),
  };
}

function sensitivePath(value: unknown): SensitivePathRef {
  const fields = object(value);
  return {
    category: messageKey(fields.category),
    kinds: list(fields.kinds, messageKey),
    match: text(fields.match),
    file: text(fields.file),
    line: integer(fields.line),
    location_kind: messageKey(fields.location_kind),
    tool: optionalText(fields.tool),
  };
}

function installScript(value: unknown): InstallScript {
  const fields = object(value);
  return {
    kind: messageKey(fields.kind),
    file: text(fields.file),
    line: integer(fields.line),
    command: text(fields.command),
  };
}

function invisibleUnicode(value: unknown): InvisibleUnicode {
  const fields = object(value);
  return {
    file: text(fields.file),
    line: integer(fields.line),
    column: integer(fields.column),
    category: messageKey(fields.category),
    codepoints: list(fields.codepoints, text),
    hidden_text: optionalText(fields.hidden_text),
    in_description: flag(fields.in_description),
    tool: optionalText(fields.tool),
    location_kind: messageKey(fields.location_kind),
  };
}

function server(value: unknown): Server {
  const fields = object(value);
  return {
    path: text(fields.path),
    name: optionalText(fields.name),
    language: text(fields.language),
    sdk: optionalText(fields.sdk),
    tools: list(fields.tools, tool),
    findings: list(fields.findings, finding),
    domains: list(fields.domains, domainRef),
    sensitive_paths: list(fields.sensitive_paths, sensitivePath),
    install_scripts: list(fields.install_scripts, installScript),
    invisible_unicode: list(fields.invisible_unicode, invisibleUnicode),
    compiled_files: list(fields.compiled_files, text),
    files_analyzed: optionalInteger(fields.files_analyzed) ?? 0,
  };
}

function source(value: unknown): Source | null {
  if (value === null || value === undefined) {
    return null;
  }
  const fields = object(value);
  return {
    kind: messageKey(fields.kind),
    name: text(fields.name),
    version: optionalText(fields.version),
    requested_version: optionalText(fields.requested_version),
    revision: optionalText(fields.revision),
    reference: optionalText(fields.reference),
    subdir: optionalText(fields.subdir),
    integrity: optionalText(fields.integrity),
    url: text(fields.url),
    artifact: messageKey(fields.artifact),
    origin: messageKey(fields.origin),
    reason: messageKey(fields.reason),
    repository: optionalText(fields.repository),
  };
}

function maliciousReport(value: unknown): MaliciousReport {
  const fields = object(value);
  return { id: text(fields.id), all_versions: flag(fields.all_versions) };
}

function packageReputation(value: unknown): PackageReputation {
  const fields = object(value);
  return {
    name: text(fields.name),
    ecosystem: text(fields.ecosystem),
    version: optionalText(fields.version),
    dependency: flag(fields.dependency),
    malicious: list(fields.malicious, maliciousReport),
  };
}

function reputation(value: unknown): Reputation | null {
  if (value === null || value === undefined) {
    return null;
  }
  const fields = object(value);
  return {
    status: messageKey(fields.status),
    queried: optionalInteger(fields.queried) ?? 0,
    packages: list(fields.packages, packageReputation),
  };
}

function candidate(value: unknown): ServerCandidate {
  const fields = object(value);
  return { path: text(fields.path), language: text(fields.language), name: optionalText(fields.name) };
}

function errorInfo(value: unknown): ErrorInfo | null {
  if (value === null || value === undefined) {
    return null;
  }
  const fields = object(value);
  return { code: messageKey(fields.code), params: textMap(fields.params) };
}

function result(value: unknown): AnalysisResult {
  const fields = object(value);
  return {
    status: oneOf(fields.status, ANALYSIS_STATUSES),
    source: source(fields.source),
    reputation: reputation(fields.reputation),
    ignored_arguments: list(fields.ignored_arguments, text),
    servers: list(fields.servers, server),
    available_servers: list(fields.available_servers, candidate),
    available_servers_truncated: flag(fields.available_servers_truncated),
    language: optionalText(fields.language),
    compiled_files: list(fields.compiled_files, text),
    notes: list(fields.notes, messageKey),
    error: errorInfo(fields.error),
    verdict: verdict(fields.verdict),
  };
}

function view(value: unknown): AnalysisView {
  const fields = object(value);
  const state = oneOf(fields.state, ANALYSIS_STATES);
  let parsed: AnalysisResult | null = null;
  if (fields.result !== null && fields.result !== undefined) {
    parsed = result(fields.result);
  }
  if ((state === "done" || state === "failed") && parsed === null) {
    fail();
  }
  if (state === "failed" && parsed !== null && parsed.verdict.color !== "gray") {
    fail();
  }
  let errorCode: string | null = null;
  if (fields.error_code !== null && fields.error_code !== undefined) {
    errorCode = messageKey(fields.error_code);
  }
  return {
    id: text(fields.id),
    input: optionalText(fields.input) ?? "",
    select: optionalText(fields.select),
    state,
    created_at: optionalText(fields.created_at),
    finished_at: optionalText(fields.finished_at),
    error_code: errorCode,
    result: parsed,
  };
}

export function parseAnalysisView(value: unknown): AnalysisView | null {
  try {
    return view(value);
  } catch (error) {
    if (error instanceof InvalidResponse) {
      return null;
    }
    throw error;
  }
}

export function parseErrorInfo(value: unknown): ErrorInfo | null {
  try {
    return errorInfo(object(value).error);
  } catch (error) {
    if (error instanceof InvalidResponse) {
      return null;
    }
    throw error;
  }
}

export function isRunning(state: AnalysisState): state is RunningState {
  return (RUNNING_STATES as readonly string[]).includes(state);
}
