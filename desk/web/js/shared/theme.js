// theme.js — the desk's look: the colour theme and the typefaces, as symbios does (a theme is a data-theme attribute
// on <html>, theme.css does the rest; Phosphor, dark and green, is the default). Kept on the board with the person's
// preferences (prefs "theme", "fonts"), so every screen showing the desk wears the same look; each screen also keeps
// its own copy, for the lock screen and the claim card, shown before the board lets this screen read anything.
import { pref, setPref } from "./prefs.js";

export const THEMES = ["phosphor", "amber", "ink", "slate", "blue", "light"];
const DEFAULT_THEME = "phosphor";
const KEY = "desk.theme";  // this screen's copy

const copy = key => { try { return localStorage.getItem(key); } catch { return null; } };
const keepCopy = (key, value) => { try { localStorage.setItem(key, value); } catch { /* a private window: not kept */ } };
const keep = (key, value) => setPref(key, value).catch(() => { /* out of reach: this screen's copy holds it */ });

export function applyTheme(id, persist = true) {
  if (id && id !== "light") document.documentElement.dataset.theme = id;
  else delete document.documentElement.dataset.theme; // light lives in :root
  if (persist) { keepCopy(KEY, id); keep("theme", id); }
  document.dispatchEvent(new Event("themechange")); // what paints its own colours (the shell) follows
}
export function currentTheme() {
  return pref("theme", null) || copy(KEY) || DEFAULT_THEME;
}
export const nextTheme = () => applyTheme(THEMES[(THEMES.indexOf(currentTheme()) + 1) % THEMES.length]);

// the two faces (tokens.css): each role, the desk speaking and reading, can wear either (Gab, 23 Nov: Instrument
// "could be an alternative for different content, or just add it to the list")
export const FACES = { departure: "Departure", instrument: "Instrument" };
export const ROLES = { ui: { label: "The desk", hint: "Windows, buttons, labels, numbers", fallback: "departure" },
  read: { label: "Reading", hint: "Notes, articles, text files", fallback: "instrument" } };
export const faceOf = role => pref("fonts", {})[role] || copy("next.font." + role) || ROLES[role].fallback;
export function applyFonts() {
  for (const role in ROLES) document.documentElement.style.setProperty(`--font-${role}`, `var(--face-${faceOf(role)})`);
}
export function setFace(role, id) {
  keepCopy("next.font." + role, id);
  keep("fonts", { ...pref("fonts", {}), [role]: id });
  applyFonts();
}

// the look at the start: the board's when it was read (main.js, after loadPrefs), else this screen's copy;
// `?theme=amber` overrides, for a look without saving
export function initTheme() {
  const q = new URLSearchParams(location.search).get("theme");
  const id = THEMES.includes(q) ? q : currentTheme();
  if (!q) keepCopy(KEY, id);
  applyTheme(id, false);
  for (const role in ROLES) keepCopy("next.font." + role, faceOf(role));
  applyFonts();
}
// a board that holds no look yet takes this screen's (the first screen to start the desk since the look moved there)
export function seedLook() {
  if (pref("theme", null) == null && copy(KEY)) keep("theme", copy(KEY));
  const fonts = {};
  for (const role in ROLES) if (copy("next.font." + role)) fonts[role] = copy("next.font." + role);
  if (pref("fonts", null) == null && Object.keys(fonts).length) keep("fonts", fonts);
}
