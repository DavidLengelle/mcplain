import { describe, expect, it } from "vitest";

import { EngineText } from "@/components/engine-text";

import { renderWithIntl } from "./intl";

describe("EngineText", () => {
  it("shows an engine text with its parameters as raw third-party text", () => {
    const { container } = renderWithIntl(
      <EngineText code="input.unsupported_host" params={{ host: "<b>gitlab.example</b>‮" }} />,
    );
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain('Only github.com links are accepted (got "<b>gitlab.example</b>');
    expect(container.querySelector("bdi")).not.toBeNull();
    expect(container.querySelector('[data-invisible="U+202E"]')).not.toBeNull();
  });

  it("writes plain numbers as they are", () => {
    const { container } = renderWithIntl(<EngineText code="input.too_long" params={{ limit: 500 }} />);
    expect(container.textContent).toBe("The input is too long (more than 500 characters).");
    expect(container.querySelector("bdi")).toBeNull();
  });

  it("speaks the language of the page", () => {
    const { container } = renderWithIntl(<EngineText code="rule.R01.title" />, "fr");
    expect(container.textContent).not.toBe("Invisible text");
    expect(container.textContent?.length).toBeGreaterThan(0);
  });

  it("says clearly when the engine texts are unavailable", () => {
    const { container } = renderWithIntl(<EngineText code="rule.R01.title" />, "en", {});
    expect(container.textContent).toBe("Text unavailable (the MCPlain service does not answer).");
  });

  it("refuses codes that are not message keys", () => {
    const { container } = renderWithIntl(<EngineText code="__proto__" />);
    expect(container.textContent).toBe("Text unavailable (the MCPlain service does not answer).");
  });
});
