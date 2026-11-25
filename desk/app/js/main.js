// The desk: windows, a dock, four apps. Shell look and structure come from symbios (islands,
// tiles, window chrome, themes); apps are custom elements and the desk only opens them.
import "./clickbridge.js";
import "./services/changes.js";
import "./components/desk-window.js";
import "./components/app-assistant.js";
import "./components/app-files.js";
import "./components/app-terminal.js";
import "./components/app-system.js";
import "./components/app-editor.js";
import "./components/app-reader.js";
import "./components/app-ask.js";
import "./components/app-music.js";
import "./components/app-video.js";
import "./components/app-slides.js";
import { current, isPlaying } from "./services/media.js";
import { bus, list, brightness } from "./services/device.js";
import "./services/slides.js";
import { I } from "./icons.js";
import { initTheme, nextTheme } from "./theme.js";

initTheme(); // before anything renders

const APPS = {
  assistant: { name: "Assistant", x: 32, y: 28, w: 460, h: 560 },
  files: { name: "Files", x: 516, y: 28, w: 520, h: 300 },
  terminal: { name: "Terminal", x: 516, y: 352, w: 560, h: 320 },
  editor: { name: "Editor", x: 516, y: 60, w: 560, h: 420 },
  reader: { name: "Reader", x: 420, y: 28, w: 640, h: 640 },
  ask: { name: "Ask", x: 380, y: 40, w: 560, h: 560 },
  music: { name: "Music", x: 1100, y: 430, w: 420, h: 540 },
  video: { name: "Video", x: 300, y: 40, w: 680, h: 520 },
  slides: { name: "Slides", x: 340, y: 60, w: 420, h: 360 },
  system: { name: "System Monitor", x: 1060, y: 28, w: 460, h: 580 },
};
const desktop = document.getElementById("desktop");
const find = id => desktop.querySelector(`desk-window[app="${id}"]`);

// open an app, or bring its window forward; a path sends Files or the Editor there
export function open(id, path) {
  let win = find(id);
  if (!win) {
    const app = APPS[id];
    win = document.createElement("desk-window");
    win.setAttribute("app", id);
    win.setAttribute("name", app.name);
    // each app has its place, pulled back inside a narrower screen
    const x = Math.max(8, Math.min(app.x, innerWidth - app.w - 8)), y = Math.max(8, Math.min(app.y, innerHeight - app.h - 96));
    win.style.cssText = `left:${x}px;top:${y}px;width:${app.w}px;height:${app.h}px;`;
    const body = document.createElement("app-" + id);
    if (path != null) body.setAttribute("path", path);
    win.append(body);
    desktop.append(win);
  } else {
    win.focusWindow();
    if (path != null) win.querySelector("app-files, app-editor, app-reader")?.open(path);
  }
}

// ---- dock: one tile per app, a dot when it runs, a bar when it is in front ----
const dockApps = document.getElementById("dock-apps");
function renderDock() {
  dockApps.replaceChildren(...Object.entries(APPS).map(([id, app]) => {
    const win = find(id);
    const t = document.createElement("button");
    t.className = "tile" + (win ? " running" : "") + (win && win.classList.contains("focused") ? " active" : "");
    t.dataset.tip = app.name;
    t.setAttribute("aria-label", app.name);
    t.innerHTML = `<span class="glyph">${I[id]}</span><span class="run-dot"></span>`;
    t.addEventListener("click", () => open(id));
    return t;
  }));
}
desktop.addEventListener("desk:change", renderDock);

// ---- now playing: a chip in the tray island while there is a track; a tap opens Music ----
const chip = document.getElementById("nowchip"), chipEq = document.getElementById("chip-eq"), chipTtl = document.getElementById("chip-ttl");
bus.addEventListener("media", () => {
  const t = current();
  chip.classList.toggle("show", !!t);
  chipEq.classList.toggle("play", isPlaying());
  chipTtl.textContent = t ? t.name : "—";
});
chip.addEventListener("click", () => open("music"));

// ---- tray: the clock; a tap moves to the next theme ----
const clkTime = document.getElementById("clk-time"), clkDate = document.getElementById("clk-date");
function tick() {
  const now = new Date();
  clkTime.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  clkDate.textContent = now.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}
tick();
setInterval(tick, 20000);
document.getElementById("tray-btn").addEventListener("click", nextTheme);

// something asked to be opened ("open the terminal", "open budget.csv", a click in Files):
// a folder goes to Files, a file to the Editor
bus.addEventListener("open", async e => {
  const { app, path } = e.detail;
  if (app !== "files") return open(app, app === "editor" || app === "reader" ? path : undefined);
  const folder = await list(path).then(() => true, () => false);
  open(folder ? "files" : "editor", path);
});
// a file dragged onto the desk goes to ~/Inbox, as it is; a recording there becomes a voice note
// in ~/Memos (voice.py on the board), and Files opens on it
desktop.addEventListener("dragover", e => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); desktop.classList.add("dropping"); } });
desktop.addEventListener("dragleave", e => { if (!desktop.contains(e.relatedTarget)) desktop.classList.remove("dropping"); });
desktop.addEventListener("drop", async e => {
  desktop.classList.remove("dropping");
  if (!e.dataTransfer.files.length) return;
  e.preventDefault();
  let went = "Inbox"; // Files opens where the inbox's rulebook put the last one
  for (const f of e.dataTransfer.files) {
    const r = await fetch(`/api/inbox?name=${encodeURIComponent(f.name)}&modified=${f.lastModified}&source=desk`, { method: "POST", body: f });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) console.warn(f.name + " not sent to the inbox: " + (d.error || r.status));
    else went = (d.went || "Inbox").split("/")[0];
  }
  setTimeout(() => { open("files", went); bus.dispatchEvent(new CustomEvent("files")); }, 300);
});

brightness(); // the light this screen was left at
// a deck started from elsewhere (another screen, the phone) opens the Slides app here too, and it takes the screen
bus.addEventListener("slide", e => { if (e.detail.deck && !find("slides")) open("slides"); });

const asked = new URLSearchParams(location.search), boot = asked.get("app");
open(boot in APPS ? boot : "assistant");
renderDock();
// the add-ons' windows (addons.py, desk.conf): each brings its element's module, its icon and its place on the dock
fetch("/api/addons").then(r => r.ok ? r.json() : []).then(async addons => {
  for (const a of addons) {
    try { await import(a.module); } catch (e) { console.warn("add-on " + a.id + " left out: " + e.message); continue; }
    APPS[a.id] = a;
    I[a.id] = a.icon;
  }
  renderDock();
  if (boot && boot in APPS && !find(boot)) open(boot);
}).catch(() => {});
// http://<desk>/?save=<link>: a link handed over from elsewhere (a phone's share, a bookmark)
// goes to the Assistant, once: the address is cleaned so a reload doesn't keep it again
if (asked.get("save")) {
  open("assistant");
  find("assistant").querySelector("app-assistant").say(asked.get("save"));
  history.replaceState(null, "", location.pathname);
}
