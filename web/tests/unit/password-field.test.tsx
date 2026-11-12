import { readdirSync, readFileSync } from "node:fs";
import { extname, join, relative } from "node:path";

import { fireEvent, screen } from "@testing-library/react";
import { useState, type FormEvent } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PasswordField, type PasswordAutoComplete } from "@/components/account/password-field";

import { renderWithIntl } from "./intl";

const SOURCE = join(process.cwd(), "src");
const COMPONENT = join("components", "account", "password-field.tsx");
const PASSWORD_TYPE = /["'`]password["'`]/;

function Harness({ autoComplete, onSubmit }: { autoComplete: PasswordAutoComplete; onSubmit: () => void }) {
  const [value, setValue] = useState("");
  const [resetCount, setResetCount] = useState(0);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setResetCount((count) => count + 1);
    onSubmit();
  }

  return (
    <form onSubmit={submit}>
      <PasswordField id="pw" label="Password" value={value} onChange={setValue} autoComplete={autoComplete} resetCount={resetCount} />
      <button type="submit">SEND</button>
    </form>
  );
}

function field(): HTMLInputElement {
  return screen.getByLabelText("Password") as HTMLInputElement;
}

function toggle(): HTMLInputElement {
  return screen.getByLabelText("Show password") as HTMLInputElement;
}

function securityAttributes(input: HTMLInputElement, autoComplete: string) {
  expect(input.getAttribute("spellcheck")).toBe("false");
  expect(input.getAttribute("autocorrect")).toBe("off");
  expect(input.getAttribute("autocapitalize")).toBe("off");
  expect(input.getAttribute("autocomplete")).toBe(autoComplete);
}

function sourceFiles(folder: string): string[] {
  return readdirSync(folder, { withFileTypes: true }).flatMap((entry) => {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(path);
    }
    if ([".ts", ".tsx"].includes(extname(entry.name))) {
      return [path];
    }
    return [];
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the password field", () => {
  it("is hidden by default, with a real checkbox linked to its label and to the field", () => {
    renderWithIntl(<Harness autoComplete="new-password" onSubmit={() => {}} />, "en");
    expect(field().type).toBe("password");
    expect(toggle().type).toBe("checkbox");
    expect(toggle().checked).toBe(false);
    expect(toggle().getAttribute("aria-controls")).toBe(field().id);
    expect(toggle().getAttribute("name")).toBeNull();
  });

  it("shows and hides what was typed, keeping the value and the cursor", () => {
    renderWithIntl(<Harness autoComplete="new-password" onSubmit={() => {}} />, "en");
    fireEvent.change(field(), { target: { value: "correct horse battery" } });
    field().setSelectionRange(7, 7);
    fireEvent.click(toggle());
    expect(field().type).toBe("text");
    expect(field().value).toBe("correct horse battery");
    expect([field().selectionStart, field().selectionEnd]).toEqual([7, 7]);
    fireEvent.click(toggle());
    expect(field().type).toBe("password");
    expect(field().value).toBe("correct horse battery");
  });

  it("keeps spellcheck, autocorrect, autocapitalize and autocomplete in both states", () => {
    for (const autoComplete of ["new-password", "current-password"] as const) {
      const { unmount } = renderWithIntl(<Harness autoComplete={autoComplete} onSubmit={() => {}} />, "en");
      securityAttributes(field(), autoComplete);
      fireEvent.click(toggle());
      securityAttributes(field(), autoComplete);
      unmount();
    }
  });

  it("never submits the form from the checkbox", () => {
    const submitted = vi.fn();
    renderWithIntl(<Harness autoComplete="current-password" onSubmit={submitted} />, "en");
    fireEvent.click(toggle());
    const enter = fireEvent.keyDown(toggle(), { key: "Enter" });
    fireEvent.keyDown(toggle(), { key: " " });
    expect(enter).toBe(false);
    expect(submitted).not.toHaveBeenCalled();
  });

  it("goes back to hidden and unchecked after a submit", () => {
    const submitted = vi.fn();
    renderWithIntl(<Harness autoComplete="current-password" onSubmit={submitted} />, "en");
    fireEvent.change(field(), { target: { value: "a long enough password" } });
    fireEvent.click(toggle());
    expect(field().type).toBe("text");
    fireEvent.click(screen.getByRole("button", { name: "SEND" }));
    expect(submitted).toHaveBeenCalledTimes(1);
    expect(field().type).toBe("password");
    expect(toggle().checked).toBe(false);
    expect(field().value).toBe("a long enough password");
  });

  it("keeps its state nowhere: no storage, no cookie, no address", () => {
    const local = vi.spyOn(Storage.prototype, "setItem");
    const before = { cookie: document.cookie, url: window.location.href };
    renderWithIntl(<Harness autoComplete="new-password" onSubmit={() => {}} />, "en");
    fireEvent.click(toggle());
    fireEvent.click(toggle());
    expect(local).not.toHaveBeenCalled();
    expect({ cookie: document.cookie, url: window.location.href }).toEqual(before);
  });

  it("speaks French too", () => {
    renderWithIntl(<PasswordField id="pw" label="Mot de passe" value="" onChange={() => {}} autoComplete="new-password" resetCount={0} />, "fr");
    expect(screen.getByLabelText("Afficher le mot de passe").getAttribute("type")).toBe("checkbox");
  });

  it("is the only place of the site that writes a password field", () => {
    const outside = sourceFiles(SOURCE)
      .filter((path) => relative(SOURCE, path) !== COMPONENT)
      .filter((path) => PASSWORD_TYPE.test(readFileSync(path, "utf-8")))
      .map((path) => relative(SOURCE, path));
    expect(outside).toEqual([]);
    expect(PASSWORD_TYPE.test(readFileSync(join(SOURCE, COMPONENT), "utf-8"))).toBe(true);
  });
});
