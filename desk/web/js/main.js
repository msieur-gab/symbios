// The desk: SymbiOS v1's shell (shell/: windows, four desktops, overview, launcher, the three-island
// dock), on a file system. Everything opens from a file: a folder in Files, a file in the app of its
// kind (kinds.js). The desktop stays clean (Gab, 23 Nov); a drop on it is placed by the rulebook.
import { bus as board, tasks } from "./shared/changes.js";
import { invalidateReserve, desktop, state } from "./shell/state.js";
import { launch, fitMaximized, retitle, fullScreen, closeWin } from "./shell/wm.js";
import { APPS, addons, load } from "./shell/loader.js";
import registry from "./apps/registry.js";
import { renderDock } from "./shell/dock.js";
import { renderPager } from "./shell/workspaces.js";
import { initDock, dockAutoEnabled, setDockAuto } from "./shell/dockhide.js";
import { connect } from "./shared/desk.js";
import { loadPrefs, prefs, pref } from "./shared/prefs.js";
import "./shell/launcher.js";
import "./shell/overview.js";
import "./shell/contextmenu.js";
import "./shell/gestures.js";
import "./shell/quick.js";
import { I } from "./shared/icons.js";
import { appFor } from "./shared/kinds.js";
import { dropOn } from "./shared/drop.js";
import { slides } from "./shared/slides.js";
import { initTheme, seedLook } from "./shared/theme.js";

initTheme();
connect({ launch, retitle, fullScreen, dockAutoEnabled, setDockAuto, apps: () => Object.values(APPS),
  running: () => [...new Set(state.wins.map(w => w.appId))],
  close: id => state.wins.filter(w => w.appId === id).forEach(closeWin) });  // the apps' door to the shell (shared/desk.js)
load(registry);  // the desk's apps into the shell, from what each says of itself (apps/registry.js)
await loadPrefs();  // the person's preferences, from the board: the look, which apps sit on the dock and in the launcher…
seedLook();  // a board with no look yet takes this screen's
initTheme();  // the board's look, the same on every screen
// the left island's overview button, or not (Settings, Dock; the overview stays at the top edge, Ctrl+↑, a right click on the dots)
const overviewButton = () => { document.getElementById("overview-btn").hidden = !pref("overviewButton", true); };
overviewButton();
prefs.addEventListener("change", () => { renderDock(); overviewButton(); });
document.querySelector("#launcher-btn .glyph").innerHTML = I.apps;
document.querySelector("#overview-btn .glyph").innerHTML = I.overview;

// a file or folder asked to open (by Files, a drop's result…): in the app of its kind
document.addEventListener("desk:open", e => launch(appFor(e.detail.item), e.detail.item, e.detail.among));

// a drop on the desktop itself (not on a window): each thing where the rulebook says (Inbox/rules.md)
desktop.addEventListener("dragover", e => {
  if (e.target !== desktop || !e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  desktop.classList.add("dropping");
});
desktop.addEventListener("dragleave", e => { if (e.target === desktop) desktop.classList.remove("dropping"); });
desktop.addEventListener("drop", e => {
  desktop.classList.remove("dropping");
  if (e.target !== desktop || !e.dataTransfer.types.includes("Files")) return;
  e.preventDefault();
  dropOn(e.dataTransfer, null);
});
addEventListener("dragover", e => e.preventDefault());  // a file dropped elsewhere must not make the browser leave the desk
addEventListener("drop", e => e.preventDefault());

// a deck started from elsewhere (another screen, the phone) opens Slides here too; full, its window comes to this
// desktop and forward, wherever it was (minimised, another desktop)
slides.addEventListener("slide", e => {
  const win = state.wins.find(w => w.appId === "slides");
  if (e.detail.deck && (!win || (e.detail.full && (win.min || win.ws !== state.curWS)))) launch("slides");
});

// what is playing, in the right island: a tap brings the Player back, wherever it is (minimised, another desktop)
const chip = document.getElementById("nowchip");
document.addEventListener("desk:media", e => {
  const m = e.detail;
  chip.classList.toggle("show", !!m);
  document.getElementById("chip-eq").classList.toggle("play", !!m?.playing);
  document.getElementById("chip-ttl").textContent = m?.name || "—";
  chip.title = m ? (m.playing ? "Playing: " : "Paused: ") + m.name : "";
});
chip.addEventListener("click", () => launch("player"));

// the board at work, in the right island: a sign while a task is pending or running, its name on hover; a tap opens
// Activity (Gab, 23 Nov: "a small sign in the right island while something runs ... showing like that there's activity")
const work = document.getElementById("workchip");
work.querySelector(".glyph").innerHTML = I.activity;
board.addEventListener("tasks", () => {
  const live = tasks.filter(t => !t.ended);
  work.hidden = !live.length;
  work.title = live.map(t => t.name + (t.state === "pending" ? " (pending)" : "")).join("\n");
});
work.addEventListener("click", () => launch("activity"));

// the clock; a tap opens the quick panel (shell/quick.js)
const clkTime = document.getElementById("clk-time"), clkDate = document.getElementById("clk-date");
function tick() {
  const now = new Date();
  clkTime.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  clkDate.textContent = now.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}
tick();
setInterval(tick, 20000);

initDock();
renderPager();
renderDock();
const boot = new URLSearchParams(location.search).get("app");  // ?app=files, for trying
addons().then(() => {  // the add-ons' windows join the apps (Mesh…)
  if (boot in APPS) launch(boot, boot === "files" ? { path: "", name: "Home", kind: "folder" } : undefined);
});
addEventListener("resize", () => { invalidateReserve(); fitMaximized(); });
