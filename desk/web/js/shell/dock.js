// dock.js — the centre island: the pinned apps, then every app with a window open. A tap opens the
// app, brings its window forward, or minimises it when it is already in front; with several windows of
// one app, each tap brings the next one. From SymbiOS v1 (core/dock.js).
import { state } from "./state.js";
import { APPS, docked } from "./loader.js";
import { launch, focusWin, toggleMin } from "./wm.js";
import { applyWorkspace } from "./workspaces.js";

export function renderDock() {
  const c = document.getElementById("dock-apps");
  const focused = state.wins.find(w => w.el.classList.contains("focused") && w.el.style.display !== "none");
  const running = [...new Set(state.wins.map(w => w.appId))], kept = docked();
  c.replaceChildren(...[...kept, ...running.filter(r => !kept.includes(r))].map(id => {
    const app = APPS[id];
    const wins = state.wins.filter(w => w.appId === id);
    const t = document.createElement("button");
    t.className = "tile" + (wins.length ? " running" : "") + (focused?.appId === id ? " active" : "");
    t.dataset.tip = app.name + (wins.length > 1 ? ` (${wins.length})` : "");
    t.setAttribute("aria-label", app.name);
    t.innerHTML = `<span class="glyph">${app.icon}</span><span class="run-dot"></span>`;
    t.onclick = () => {
      if (!wins.length) return launch(id, id === "files" ? { path: "", name: "Home", kind: "folder" } : undefined);
      const order = [...wins].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
      const w = focused?.appId === id && wins.length > 1 ? order[(order.indexOf(focused) + 1) % order.length] : order.find(x => x === focused) || order.at(-1);
      if (w.ws !== state.curWS) { w.ws = state.curWS; applyWorkspace(); focusWin(w); }
      else if (w.min) toggleMin(w, false);
      else if (focused === w && wins.length === 1) toggleMin(w, true);
      else focusWin(w);
    };
    return t;
  }));
}
