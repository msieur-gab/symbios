// theme.js — apply and remember the colour theme, as symbios does: a theme is a data-theme
// attribute on <html>, theme.css does the rest. Phosphor (dark and green) is the default.
const KEY = "desk.theme";
export const THEMES = ["phosphor", "amber", "ink", "slate", "blue", "light"];
const DEFAULT_THEME = "phosphor";

export function applyTheme(id, persist = true) {
  if (id && id !== "light") document.documentElement.dataset.theme = id;
  else delete document.documentElement.dataset.theme; // light lives in :root
  if (persist) { try { localStorage.setItem(KEY, id); } catch { /* not kept */ } }
  document.dispatchEvent(new Event("themechange")); // what paints its own colours (the shell) follows
}
export function currentTheme() {
  try { return localStorage.getItem(KEY) || DEFAULT_THEME; } catch { return DEFAULT_THEME; }
}
// `?theme=amber` overrides, for a look without saving
export function initTheme() {
  const q = new URLSearchParams(location.search).get("theme");
  applyTheme(THEMES.includes(q) ? q : currentTheme(), false);
}
export const nextTheme = () => applyTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]);
