import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AnalysisForm } from "@/components/analysis-form";

import { renderWithIntl } from "./intl";

const push = vi.fn();

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push }),
}));

const ID = "8b0f9a52-3c41-4e5e-9a0b-1c2d3e4f5a6b";

function answer(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function submit(value: string) {
  fireEvent.change(screen.getByLabelText("MCP server to check"), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
}

function errorZone(): HTMLElement {
  const zone = document.getElementById("analysis-error");
  if (zone === null) {
    throw new Error("the error zone is missing");
  }
  return zone;
}

describe("analysis form", () => {
  beforeEach(() => {
    push.mockReset();
  });

  it("announces its errors to screen readers, under the field", () => {
    renderWithIntl(<AnalysisForm />);
    expect(errorZone().getAttribute("aria-live")).toBe("polite");
    expect(screen.getByLabelText("MCP server to check").getAttribute("aria-describedby")).toContain("analysis-error");
  });

  it("asks for something when the field is empty, without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    renderWithIntl(<AnalysisForm />);
    submit("   ");
    expect(errorZone().textContent).toBe("Paste a GitHub link, an npx command or a uvx command.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("sends the trimmed text as JSON and goes to the analysis page", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(202, { id: ID, state: "queued" }));
    renderWithIntl(<AnalysisForm />);
    submit("   uvx mcp-server-fetch  ");
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/analyses/${ID}`));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/analyses");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(String(init?.body))).toEqual({ input: "uvx mcp-server-fetch" });
  });

  it("shows the engine message of a 400, with its parameters as plain text", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      answer(400, { error: { code: "input.unsupported_host", params: { host: "<i>gitlab.example</i>" } } }),
    );
    renderWithIntl(<AnalysisForm />);
    submit("https://gitlab.example/a/b");
    await waitFor(() => expect(errorZone().textContent).toContain('Only github.com links are accepted (got "'));
    expect(errorZone().textContent).toContain("<i>gitlab.example</i>");
    expect(errorZone().querySelector("i")).toBeNull();
    expect(screen.getByLabelText("MCP server to check").getAttribute("aria-invalid")).toBe("true");
    expect(push).not.toHaveBeenCalled();
  });

  it("says the queue is full on 503", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(answer(503, { error: { code: "api.queue_full", params: {} } }));
    renderWithIntl(<AnalysisForm />, "fr");
    fireEvent.change(screen.getByLabelText("Serveur MCP à vérifier"), { target: { value: "uvx mcp-server-fetch" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyser" }));
    await waitFor(() => expect(errorZone().textContent).toBe("La file est pleine, réessaie dans une minute."));
  });

  it("says that MCPlain does not answer when the network fails or the answer is strange", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    renderWithIntl(<AnalysisForm />);
    submit("uvx mcp-server-fetch");
    await waitFor(() => expect(errorZone().textContent).toBe("MCPlain does not answer right now. Try again in a few minutes."));
    fetchMock.mockResolvedValue(answer(202, { id: "not-a-uuid" }));
    submit("uvx mcp-server-fetch");
    await waitFor(() => expect(errorZone().textContent).toBe("MCPlain does not answer right now. Try again in a few minutes."));
    expect(push).not.toHaveBeenCalled();
  });

  it("fills the field with an example", () => {
    renderWithIntl(<AnalysisForm />);
    fireEvent.click(screen.getByRole("button", { name: "Fill the field with npx -y @modelcontextprotocol/server-filesystem" }));
    expect((screen.getByLabelText("MCP server to check") as HTMLInputElement).value).toBe(
      "npx -y @modelcontextprotocol/server-filesystem",
    );
  });

  it("refuses more than 500 characters in the field", () => {
    renderWithIntl(<AnalysisForm />);
    expect(screen.getByLabelText("MCP server to check").getAttribute("maxlength")).toBe("500");
  });
});
