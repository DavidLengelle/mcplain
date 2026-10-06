export const THEME_STORAGE_KEY = "mcplain-theme";
export const THEME_SCRIPT_PATH = "/theme.js";
export const THEME_CHOICES = ["system", "light", "dark"] as const;
export const THEME_CLASSES = { light: "th-light", dark: "th-dark" } as const;
export const THEME_EVENT = "mcplain-theme-change";

export type ThemeChoice = (typeof THEME_CHOICES)[number];

export function parseThemeChoice(value: string | null): ThemeChoice {
  if (value === "light" || value === "dark") {
    return value;
  }
  return "system";
}

export function readThemeChoice(): ThemeChoice {
  try {
    return parseThemeChoice(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return "system";
  }
}

export function applyThemeClass(root: HTMLElement, choice: ThemeChoice): void {
  root.classList.remove(THEME_CLASSES.light, THEME_CLASSES.dark);
  if (choice !== "system") {
    root.classList.add(THEME_CLASSES[choice]);
  }
}

export function saveThemeChoice(choice: ThemeChoice): void {
  try {
    if (choice === "system") {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, choice);
    }
  } catch {
    return;
  }
}

export function chooseTheme(choice: ThemeChoice): void {
  saveThemeChoice(choice);
  applyThemeClass(document.documentElement, choice);
  window.dispatchEvent(new Event(THEME_EVENT));
}

export function subscribeToTheme(onChange: () => void): () => void {
  window.addEventListener(THEME_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(THEME_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}
