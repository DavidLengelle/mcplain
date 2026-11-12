import { mkdirSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "./test";

const SCREENS = join(__dirname, "..", "..", "test-results", "screens");
const THEMES = ["light", "dark"] as const;
const WIDTHS = [1280, 390] as const;
const TYPED = "correct horse battery";

for (const theme of THEMES) {
  for (const width of WIDTHS) {
    test(`the sign-up password can be shown then hidden, ${theme} theme, ${width} px`, async ({ page }) => {
      mkdirSync(SCREENS, { recursive: true });
      await page.setViewportSize({ width, height: 900 });
      await page.emulateMedia({ colorScheme: theme });
      await page.goto("/fr/account/sign-up");
      const field = page.getByLabel("Mot de passe", { exact: true });
      const toggle = page.getByRole("checkbox", { name: "Afficher le mot de passe" });
      await expect(field).toHaveAttribute("type", "password");
      await expect(toggle).not.toBeChecked();
      await field.fill(TYPED);
      await field.press("Home");
      await field.press("ArrowRight");
      await field.press("ArrowRight");
      await toggle.check();
      await expect(field).toHaveAttribute("type", "text");
      await expect(field).toHaveValue(TYPED);
      await expect(field).toHaveAttribute("autocomplete", "new-password");
      await expect(field).toHaveAttribute("spellcheck", "false");
      await expect(page).toHaveURL(/\/fr\/account\/sign-up$/);
      expect(await field.evaluate((element: HTMLInputElement) => element.selectionStart)).toBe(2);
      await page.screenshot({ path: join(SCREENS, `password-shown-${theme}-${width}.png`), fullPage: true });
      await toggle.press("Space");
      await expect(field).toHaveAttribute("type", "password");
      await expect(toggle).not.toBeChecked();
      await toggle.press("Space");
      await expect(field).toHaveAttribute("type", "text");
      await toggle.press("Enter");
      await expect(page).toHaveURL(/\/fr\/account\/sign-up$/);
      await expect(page.getByTestId("sign-up-done")).toHaveCount(0);
      await toggle.uncheck();
      await expect(field).toHaveAttribute("type", "password");
      await expect(field).toHaveValue(TYPED);
      expect(await page.evaluate(() => [window.localStorage.length, window.sessionStorage.length, window.location.search])).toEqual([0, 0, ""]);
      await page.screenshot({ path: join(SCREENS, `password-hidden-${theme}-${width}.png`), fullPage: true });
    });
  }
}
