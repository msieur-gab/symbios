// The person's preferences, kept on the board (prefs.py, ~/.config/desk/prefs.json): every screen showing the desk is
// the same desk. Read once when the desk starts; a change is said at once here ("change" on prefs), then kept.
let now = {};
export const prefs = new EventTarget();

export async function loadPrefs() {
  try {
    const r = await fetch("/api/prefs");
    if (r.ok) now = await r.json();
  } catch { /* none kept yet, or the board is out of reach: the apps' own defaults */ }
}
// one preference, or the fallback when the person never set it
export const pref = (key, fallback) => key in now ? now[key] : fallback;
// an app's own preferences, kept under its name ("app.files": {"view": "grid"}): its block in Settings sets them
export const appPref = (app, key, fallback) => pref("app." + app, {})[key] ?? fallback;
export const setAppPref = (app, key, value) => setPref("app." + app, { ...pref("app." + app, {}), [key]: value });
// one preference set (null forgets it, back to the default); the answer is when the board has kept it
export async function setPref(key, value) {
  if (value == null) delete now[key]; else now[key] = value;
  prefs.dispatchEvent(new CustomEvent("change", { detail: { key } }));
  const r = await fetch("/api/prefs", { method: "POST", headers: { "X-Desk": "1", "Content-Type": "application/json" }, body: JSON.stringify({ [key]: value ?? null }) });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || "the board answered " + r.status);
}
