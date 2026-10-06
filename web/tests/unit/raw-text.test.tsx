import { fireEvent, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RawText } from "@/components/raw-text";

import { renderWithIntl } from "./intl";

const RIGHT_TO_LEFT_OVERRIDE = "\u202E";
const TAG_A = "\u{E0041}";
const TAG_B = "\u{E0042}";

function badges(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll("[data-invisible]"), (element) => element.getAttribute("data-invisible") ?? "");
}

describe("RawText", () => {
  it("shows an HTML tag as text and never creates the element", () => {
    const { container } = renderWithIntl(<RawText value={"<script>alert(1)</script><img src=x onerror=alert(2)>"} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script><img src=x onerror=alert(2)>");
  });

  it("isolates the text in a bdi element with unicode-bidi isolate and pre-wrap", () => {
    const { container } = renderWithIntl(<RawText value="text" />);
    const isolated = container.querySelector("bdi");
    expect(isolated).not.toBeNull();
    expect(isolated?.className).toContain("[unicode-bidi:isolate]");
    expect(isolated?.className).toContain("whitespace-pre-wrap");
  });

  it("turns U+202E into a visible badge, so it cannot reverse the text", () => {
    const { container } = renderWithIntl(<RawText value={`invoice${RIGHT_TO_LEFT_OVERRIDE}fdp.exe`} />);
    expect(container.textContent).not.toContain(RIGHT_TO_LEFT_OVERRIDE);
    expect(badges(container)).toEqual(["U+202E"]);
    const badge = container.querySelector('[data-invisible="U+202E"]');
    expect(badge?.textContent).toContain("U+202E");
    expect(badge?.getAttribute("title")).toBe("invisible character");
    const visible = container.textContent ?? "";
    expect(visible.indexOf("invoice")).toBeLessThan(visible.indexOf("U+202E"));
    expect(visible.indexOf("U+202E")).toBeLessThan(visible.indexOf("fdp.exe"));
  });

  it("shows each Unicode tag character as a badge", () => {
    const { container } = renderWithIntl(<RawText value={`hello${TAG_A}${TAG_B}`} />);
    expect(container.textContent).not.toContain(TAG_A);
    expect(container.textContent).not.toContain(TAG_B);
    expect(badges(container)).toEqual(["U+E0041", "U+E0042"]);
  });

  it("names the badge in French", () => {
    const { container } = renderWithIntl(<RawText value={"a\u200Bb"} />, "fr");
    expect(container.querySelector("[data-invisible]")?.getAttribute("title")).toBe("caractère invisible");
  });

  it("cuts a long text and shows all of it on demand", () => {
    const long = `${"a".repeat(30)}${"b".repeat(30)}`;
    renderWithIntl(<RawText value={long} limit={30} />);
    expect(screen.queryByText("b".repeat(30), { exact: false })).toBeNull();
    const button = screen.getByRole("button", { name: "Show all" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(screen.getByText(long)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show less" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("never cuts a tag character in half", () => {
    const { container } = renderWithIntl(<RawText value={`${TAG_A}${TAG_B}${TAG_A}`} limit={2} />);
    expect(badges(container)).toEqual(["U+E0041", "U+E0042"]);
    expect(container.textContent).not.toMatch(/[\uD800-\uDFFF]/);
  });

  it("leaves short texts without a button", () => {
    renderWithIntl(<RawText value="short" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
