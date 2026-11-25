// Settings: the desk's preferences, a page each, chosen in a sidebar (Gab, 24 Nov: like Zorin OS's; "why these things
// are split? They belong to the same app"). The desk's own pages: the look (themes, typefaces) and the dock, from what
// the desk and SymbiOS v1 had (Gab, 23 Nov: "theme and settings ... are things we should keep"). Then a page per app,
// everything about it together: where it shows, the launcher and the dock (Gab, 24 Nov: "the place where we can define
// which application is making it to the app launcher bar"), then the settings its description brings ("the apps that
// we build and we declare in the registry should declare their settings inside the setting panel"). Made of the design
// system's pieces only: .app-split, .app-side, .row, .app-bar, and Settings' sections (.set-sec, .set-row).
import { THEMES, currentTheme, applyTheme, FACES, ROLES, faceOf, setFace } from "../../shared/theme.js";
import { dockHides, setDockHides, apps } from "../../shared/desk.js";
import { pref, setPref } from "../../shared/prefs.js";
import { I } from "../../shared/icons.js";
import { el } from "../../utils/dom.js";
import { row, toggle, choice, section } from "../../shared/controls.js";

// ---- Appearance: a theme's swatch wears the theme itself ([data-theme] sets its colours on the button) ----
export function swatches(onPick) {
  return THEMES.map(id => {
    const b = el("button", "theme-sw" + (id === currentTheme() ? " active" : ""), id);
    b.dataset.theme = id;
    b.onclick = () => { applyTheme(id); onPick?.(id); };
    return b;
  });
}

// ---- Typefaces: each role, the desk speaking and reading, wears one of the two faces (theme.js) ----
const faces = role => choice(Object.entries(FACES), faceOf(role), id => setFace(role, id), (b, id) => { b.style.fontFamily = `var(--face-${id})`; });

// ---- This board: who owns it, and releasing it (Gab, 24 Nov: "unclaim a board from plugging the board in a computer,
// unlocking it via the phone ... and then release it from there"; "all the files are kept"). Asked from a screen on the
// board's cable or its own; the owner's phone confirms; then the desk shows its QR card again (gate.js) ----
function boardPage() {
  const owner = el("small", "", "…"), said = el("small", "", "");
  const go = el("button", "btn", "Release…");
  go.type = "button";
  go.disabled = true;
  const words = el("div");
  words.append(el("b", "", "Release this board"), said);
  const releaseRow = el("div", "set-row");
  releaseRow.append(words, go);
  const ownerRow = el("div", "set-row"), who = el("div");
  who.append(el("b", "", "Its owner"), owner);
  ownerRow.append(who);
  const idle = "Its phone no longer owns it; the files stay. It then shows its QR code, to be claimed again.";
  fetch("/api/trust/owner").then(r => r.ok ? r.json() : null).catch(() => null).then(o => {
    if (!o) { owner.textContent = "No phone owns this desk."; said.textContent = ""; return; }
    owner.textContent = (o.name || "a phone") + (o.since ? ", since " + o.since : "");
    go.disabled = !o.release;
    said.textContent = o.release ? idle : "From a computer on the board’s USB cable, or its own screen.";
  });
  go.onclick = async () => {
    go.disabled = true;
    const r = await fetch("/api/trust/release", { method: "POST" }).catch(() => null);
    const asked = r?.ok ? await r.json().catch(() => null) : null;
    if (!asked) { said.textContent = "The desk refused: " + ((r && (await r.json().catch(() => ({}))).error) || "out of reach"); go.disabled = false; return; }
    said.textContent = "Confirm on the owner’s phone: the companion asks now.";
    let state = "waiting";
    while (state === "waiting") {
      try { ({ state } = await fetch("/api/trust/release/wait?id=" + encodeURIComponent(asked.id)).then(r => r.json())); }
      catch { state = "gone"; }
    }
    // released: the desk's wait (gate.js) starts the page again, on the QR card
    said.textContent = state === "released" ? "Released." : state === "refused" ? "The phone refused." : "Not answered in time. " + idle;
    go.disabled = state === "released";
  };
  return [section("", [ownerRow, releaseRow])];
}

// the desk's own pages
const DESK = [
  { id: "appearance", name: "Appearance", draw: () => { const grid = el("div", "theme-grid"); grid.append(...swatches()); return [section("Theme", [grid])]; } },
  { id: "typefaces", name: "Typefaces", draw: () => [section("", Object.entries(ROLES).map(([role, r]) => row(r.label, r.hint, faces(role))))] },
  { id: "dock", name: "Dock", draw: () => [section("", [
    row("Hide the dock", "It slides away, and comes back at the bottom edge", toggle("Hide the dock", dockHides(), setDockHides)),
    // Gab, 24 Nov: "to be able to activate or deactivate the overview icon in the left island"
    row("Overview button", "In the left island. Without it, the overview is at the top edge, Ctrl+↑, or a right click on the dots",
      toggle("Overview button", pref("overviewButton", true), on => setPref("overviewButton", on)))])] },
  { id: "board", name: "This board", draw: boardPage },
];

// an app's page: where it shows (the person's choice, kept on the board, prefs "apps", over the app's own word), then
// what its description's settings bring (sections, or rows put in one)
function appPage(a) {
  const keep = where => on => { const all = pref("apps", {}); return setPref("apps", { ...all, [a.id]: { ...all[a.id], [where]: on } }); };
  const chosen = pref("apps", {})[a.id] || {};
  const where = section("Where it shows", [
    row("In the launcher", "", toggle(a.name + " in the launcher", chosen.launcher ?? !!a.launcher, keep("launcher"))),
    row("On the dock", "Kept there, even when closed", toggle(a.name + " on the dock", chosen.dock ?? !!a.dock, keep("dock")))]);
  const own = typeof a.settings === "function" ? a.settings() : [];
  return [where, ...(own.every(n => n.tagName === "SECTION") ? own : [section("", own)])];
}

class AppSettings extends HTMLElement {
  connectedCallback() {
    this.here ??= "appearance";
    this.render();
    this.onTheme = () => this.render();
    document.addEventListener("themechange", this.onTheme);
  }
  closing() { document.removeEventListener("themechange", this.onTheme); }
  render() {
    const appList = apps().filter(a => a.launcher || typeof a.settings === "function");
    const pages = [...DESK, ...appList.map(a => ({ id: "app:" + a.id, name: a.name, icon: a.icon, draw: () => appPage(a) }))];
    const page = pages.find(p => p.id === this.here) || pages[0];
    const split = el("div", "app-split pages" + (this.reading ? " reading" : ""));
    const side = el("nav", "app-side"), view = el("div", "app-page"), bar = el("div", "app-bar");
    side.setAttribute("aria-label", "Settings' pages");
    const item = p => {
      const b = el("button", "row" + (p.id === page.id ? " here" : ""));
      b.type = "button";
      if (p.icon) { const g = el("span", "g"); g.innerHTML = p.icon; b.append(g); }
      b.append(el("span", "name", p.name));
      b.onclick = () => { this.here = p.id; this.reading = true; this.render(); };
      return b;
    };
    side.append(el("div", "eyebrow", "The desk"), ...DESK.map(item), el("div", "eyebrow", "Apps"), ...pages.slice(DESK.length).map(item));
    const back = el("button", "ib back");
    back.type = "button";
    back.setAttribute("aria-label", "Settings' pages");
    back.innerHTML = I.back;
    back.onclick = () => { this.reading = false; this.render(); };
    if (page.icon) { const g = el("span", "g"); g.innerHTML = page.icon; bar.append(back, g); } else bar.append(back);
    bar.append(el("b", "grow", page.name));
    view.append(bar, ...page.draw());
    split.append(side, view);
    this.replaceChildren(split);
  }
}

export default {
  id: "settings",
  name: "Settings",
  said: ["desk settings", "preferences"],
  icon: I.settings,
  size: [720, 560],
  launcher: true,
  element: AppSettings,
};
