// loader.js — loads the apps into the shell: those of the registry (apps/registry.js), from what each says of
// itself, and the add-ons' windows the board announces. Each opens
// one element, given a file or a folder of the home, or nothing. The launcher shows those that ask for it; the dock
// keeps those that ask for it (Gab, 23 Nov: the Terminal, the Settings and the Monitor sit with the apps, "but not
// within the shortcut bar"). A running app shows on the dock while it runs, pinned or not.
import { OPENS } from "../shared/kinds.js";
import { pref } from "../shared/prefs.js";

const element = tag => (body, item, among) => {
  const el = document.createElement(tag);
  body.append(el);
  el.show?.(item, among);
  return el;
};

export const APPS = {};

// where an app shows: the person's choice in Settings (prefs "apps": {id: {dock, launcher}}), else the app's own word
const chosen = (id, where) => pref("apps", {})[id]?.[where] ?? APPS[id][where];
export const onDock = id => chosen(id, "dock");
export const inLauncher = id => chosen(id, "launcher");
export const docked = () => Object.keys(APPS).filter(onDock);  // the dock's kept apps, in the registry's order

// the registry's apps, from what each says of itself: its element registered, the kinds it opens told to the table of
// kinds
export function load(list) {
  for (const app of list) {
    const tag = "app-" + app.id;
    if (!customElements.get(tag)) customElements.define(tag, app.element);
    APPS[app.id] = { many: false, launcher: false, dock: false, opens: [], ...app, render: element(tag) };
    for (const kind of APPS[app.id].opens) OPENS[kind] ??= app.id;
  }
}

// the add-ons' windows (the server's addons.py, desk.conf: desk-meshtastic's Mesh…): each brings its element's module,
// its icon and its size, and sits in the launcher with the apps. One that fails to load is left out, and said.
export async function addons() {
  const list = await fetch("/api/addons").then(r => r.ok ? r.json() : []).catch(() => []);
  for (const a of list) {
    if (!/^[a-z][a-z0-9-]*$/.test(a.id || "") || a.id in APPS) continue;
    try { await import(a.module); } catch (e) { console.warn("add-on " + a.id + " left out: " + e.message); continue; }
    APPS[a.id] = { id: a.id, name: a.name, icon: a.icon, size: [a.w || 420, a.h || 560], launcher: true, many: false, opens: [], render: element("app-" + a.id) };
  }
}
