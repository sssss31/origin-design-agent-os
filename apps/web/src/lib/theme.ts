export type ThemeChoice = "system" | "light" | "dark";
const KEY = "origin.theme";

export function readTheme(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(choice: ThemeChoice): void {
  try {
    if (choice === "system") {
      localStorage.removeItem(KEY);
      document.documentElement.removeAttribute("data-theme");
    } else {
      localStorage.setItem(KEY, choice);
      document.documentElement.setAttribute("data-theme", choice);
    }
  } catch {
    /* storage unavailable */
  }
}
