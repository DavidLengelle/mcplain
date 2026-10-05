import type { Page, Route } from "@playwright/test";

export const ID = "5b0c6f2e-8d3a-4c1b-9e7f-0a1b2c3d4e5f";
export const SECOND_ID = "9c8b7a65-4321-4fed-8cba-987654321000";
export const ZERO_WIDTH_SPACE = "​";

type Json = Record<string, unknown>;

const SOURCE: Json = {
  kind: "pypi",
  name: "weather-demo",
  version: "1.2.0",
  requested_version: "latest",
  revision: null,
  reference: null,
  subdir: null,
  integrity: `sha256:${"a".repeat(64)}`,
  url: "https://files.pythonhosted.org/packages/demo/weather_demo-1.2.0-py3-none-any.whl",
  artifact: "wheel",
  origin: "published_package",
  reason: "source.requested_package",
  repository: null,
};

function tool(name: string, description: string, findings: Json[]): Json {
  return {
    name,
    name_is_dynamic: false,
    description,
    description_is_dynamic: false,
    parameters: [{ name: "url", type: "str", description: "Address of the page" }],
    parameters_are_dynamic: false,
    file: "weather_demo/server.py",
    line: 10,
    declaration: "decorator",
    location_kind: "server_code",
    title: null,
    title_is_dynamic: false,
    annotations: { readOnlyHint: true },
    annotations_are_dynamic: false,
    findings,
    gaps: [],
  };
}

function server(tools: Json[]): Json {
  return {
    path: ".",
    name: "weather-demo",
    language: "python",
    sdk: "mcp",
    tools,
    findings: [],
    domains: [
      {
        domain: "api.weather.example",
        url: "https://api.weather.example/v1",
        file: "weather_demo/server.py",
        line: 5,
        location_kind: "server_code",
        tool: null,
      },
    ],
    sensitive_paths: [],
    install_scripts: [],
    invisible_unicode: [],
    flows: [],
    files_analyzed: 2,
  };
}

function verdict(color: string, alerts: Json[], reasons: string[] = []): Json {
  return { color, alerts, reasons, rules_version: "1", rules_count: 20, contacted_domains: [] };
}

function result(status: string, servers: Json[], verdictValue: Json, extra: Json = {}): Json {
  return {
    status,
    source: SOURCE,
    reputation: { status: "checked", queried: 1, packages: [] },
    ignored_arguments: [],
    servers,
    available_servers: [],
    available_servers_truncated: false,
    language: null,
    compiled_files: [],
    notes: [],
    error: null,
    verdict: verdictValue,
    ...extra,
  };
}

export function view(state: string, body: Json | null, extra: Json = {}): Json {
  let finished: string | null = null;
  if (state === "done" || state === "failed") {
    finished = "2026-10-05T10:00:05+00:00";
  }
  return {
    id: ID,
    input: "uvx weather-demo",
    select: null,
    state,
    created_at: "2026-10-05T10:00:00+00:00",
    finished_at: finished,
    result: body,
    error_code: null,
    ...extra,
  };
}

export function orangeView(): Json {
  const network = {
    capability: "network",
    file: "weather_demo/server.py",
    line: 42,
    column: 8,
    snippet: "response = await client.get(url)",
    function: "fetch_page",
    location_kind: "server_code",
    call_chain: [],
    shared_by_tools: false,
    outside: null,
    url_kind: "dynamic",
  };
  const alert = {
    rule: "O01",
    color: "orange",
    kind: "power_to_know",
    tool: "fetch_page",
    shared_by_tools: false,
    outside: null,
    file: "weather_demo/server.py",
    line: 42,
    function: "fetch_page",
    source: null,
    steps: [],
    quote: "response = await client.get(url)",
    detail: "httpx.AsyncClient.get",
  };
  const fetchPage = tool("fetch_page", "Fetches a page and returns its text.", [network]);
  return view("done", result("ok", [server([fetchPage])], verdict("orange", [alert])));
}

export function redView(): Json {
  const description = `Returns the forecast for a city.${ZERO_WIDTH_SPACE}${ZERO_WIDTH_SPACE}`;
  const alert = {
    rule: "R01",
    color: "red",
    kind: "suspicious_use",
    tool: "get_forecast",
    shared_by_tools: false,
    outside: null,
    file: "weather_demo/server.py",
    line: 12,
    function: null,
    source: null,
    steps: [],
    quote: description,
    detail: "zero_width_run",
  };
  const forecast = tool("get_forecast", description, []);
  return view("done", result("ok", [server([forecast])], verdict("red", [alert])));
}

export function failedView(): Json {
  const gray = verdict("gray", [], ["status.error"]);
  const body = result("error", [], gray, { error: { code: "job.atelier_timeout", params: {} } });
  return view("failed", body, { error_code: "atelier_timeout" });
}

export function multipleView(): Json {
  const gray = verdict("gray", [], ["status.multiple_servers"]);
  const body = result("multiple_servers", [], gray, {
    available_servers: [
      { path: "servers/alpha", language: "python", name: "alpha" },
      { path: "servers/beta", language: "typescript", name: null },
    ],
  });
  return view("done", body, { input: "https://github.com/example/monorepo" });
}

export async function fulfill(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function serveAnalysis(page: Page, answers: Json[], id: string = ID): Promise<string[]> {
  const seen: string[] = [];
  let index = 0;
  await page.route(`**/api/analyses/${id}`, async (route) => {
    seen.push(route.request().method());
    const answer = answers[Math.min(index, answers.length - 1)];
    index += 1;
    await fulfill(route, 200, answer);
  });
  return seen;
}
