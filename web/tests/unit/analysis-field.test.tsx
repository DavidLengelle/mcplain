import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisField } from "@/components/analysis-field";

import { renderWithIntl } from "./intl";

const push = vi.fn();

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push }),
}));

const ID = "8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";
const FIELD = "MCP server link";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function submit(value: string) {
  fireEvent.change(screen.getByLabelText(FIELD), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "ANALYZE" }));
}

function errorZone(): HTMLElement {
  const zone = document.getElementById("home-error");
  if (zone === null) {
    throw new Error("the error zone is missing");
  }
  return zone;
}

describe("analysis field of the home page", () => {
  beforeEach(() => {
    push.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("has a visible label and announces its errors to screen readers, under the field", () => {
    renderWithIntl(<AnalysisField variant="hero" />);
    const label = document.querySelector('label[for="home-input"]');
    expect(label?.textContent).toBe(FIELD);
    expect(label?.className).not.toContain("sr-only");
    expect(errorZone().getAttribute("aria-live")).toBe("polite");
    expect(screen.getByLabelText(FIELD).getAttribute("aria-describedby")).toBe("home-error");
  });

  it("asks for something when the field is empty, without calling the API", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderWithIntl(<AnalysisField variant="hero" />);
    submit("   ");
    expect(errorZone().textContent).toBe("Paste a GitHub link, an npx command or a uvx command.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the trimmed text as JSON and goes to the analysis page", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(202, { id: ID, state: "queued" }));
    renderWithIntl(<AnalysisField variant="hero" />);
    submit("   uvx mcp-server-fetch  ");
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/analyses/${ID}`));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/analyses");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ input: "uvx mcp-server-fetch" });
  });

  it("shows only the busy text on its button while sending", async () => {
    vi.spyOn(globalThis, "fetch").mockReturnValue(new Promise(() => {}));
    renderWithIntl(<AnalysisField variant="hero" />, "fr");
    fireEvent.change(screen.getByLabelText("Lien du serveur MCP"), { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.click(screen.getByRole("button", { name: "ANALYSER" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "ENVOI…" })).toHaveProperty("disabled", true));
  });

  it("shows the engine message of a 400, with its parameters as plain text", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      answer(400, { error: { code: "input.unsupported_host", params: { host: "<i>gitlab.example</i>" } } }),
    );
    renderWithIntl(<AnalysisField variant="hero" />);
    submit("https://gitlab.example/a/b");
    await waitFor(() => expect(errorZone().textContent).toContain('Only github.com links are accepted (got "'));
    expect(errorZone().textContent).toContain("<i>gitlab.example</i>");
    expect(errorZone().querySelector("i")).toBeNull();
    expect(screen.getByLabelText(FIELD).getAttribute("aria-invalid")).toBe("true");
    expect(push).not.toHaveBeenCalled();
  });

  it("says the queue is full on 503", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(503, { error: { code: "api.queue_full", params: {} } }));
    renderWithIntl(<AnalysisField variant="hero" />, "fr");
    fireEvent.change(screen.getByLabelText("Lien du serveur MCP"), { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.click(screen.getByRole("button", { name: "ANALYSER" }));
    await waitFor(() => expect(errorZone().textContent).toBe("La file est pleine, réessaie dans une minute."));
  });

  it("says that MCPlain does not answer when the network fails or the answer is strange", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    renderWithIntl(<AnalysisField variant="hero" />);
    submit("uvx mcp-server-fetch");
    await waitFor(() => expect(errorZone().textContent).toBe("MCPlain does not answer right now. Try again in a few minutes."));
    fetchMock.mockResolvedValue(answer(202, { id: "not-a-uuid" }));
    submit("uvx mcp-server-fetch");
    await waitFor(() => expect(errorZone().textContent).toBe("MCPlain does not answer right now. Try again in a few minutes."));
    expect(push).not.toHaveBeenCalled();
  });

  it("fills the field with an example and starts its analysis at once", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(202, { id: ID, state: "queued" }));
    renderWithIntl(<AnalysisField variant="hero" />);
    fireEvent.click(screen.getByRole("button", { name: "Analyze npx -y @modelcontextprotocol/server-filesystem" }));
    expect((screen.getByLabelText(FIELD) as HTMLInputElement).value).toBe("npx -y @modelcontextprotocol/server-filesystem");
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/analyses/${ID}`));
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      input: "npx -y @modelcontextprotocol/server-filesystem",
    });
  });

  it("shows the GitHub example without its scheme but sends the whole link", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(202, { id: ID, state: "queued" }));
    renderWithIntl(<AnalysisField variant="hero" />);
    const button = screen.getByRole("button", {
      name: "Analyze github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    });
    expect(button.textContent).toBe("github.com/modelcontextprotocol/servers/tree/main/src/fetch");
    fireEvent.click(button);
    await waitFor(() => expect(push).toHaveBeenCalled());
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({
      input: "https://github.com/modelcontextprotocol/servers/tree/main/src/fetch",
    });
  });

  it("offers exactly three examples, as real buttons", () => {
    renderWithIntl(<AnalysisField variant="hero" />);
    const examples = document.querySelectorAll("button[data-example]");
    expect(examples).toHaveLength(3);
    examples.forEach((example) => expect(example.getAttribute("type")).toBe("button"));
  });

  it("refuses more than 500 characters in the field", () => {
    renderWithIntl(<AnalysisField variant="hero" />);
    expect(screen.getByLabelText(FIELD).getAttribute("maxlength")).toBe("500");
  });

  it("keeps a hidden label and no example in the header variant", () => {
    renderWithIntl(<AnalysisField variant="header" />);
    expect(screen.getByLabelText("Link of the MCP server to analyze").id).toBe("header-input");
    expect(document.querySelectorAll("button[data-example]")).toHaveLength(0);
  });
});
