// workspaces.js — the four desktops and the dots on the left island that switch them. From SymbiOS v1.
import { state, WORKSPACES } from "./state.js";
import { renderDock } from "./dock.js";
import { openOverview } from "./overview.js";

export function switchWS(i) { state.curWS = i; applyWorkspace(); renderPager(); }

export function applyWorkspace() {
  state.wins.forEach(w => { w.el.style.display = w.ws === state.curWS && !w.min ? "flex" : "none"; });
  renderDock();
}

export function renderPager() {
  const p = document.getElementById("pager");
  p.replaceChildren();
  for (let i = 0; i < WORKSPACES; i++) {
    const b = document.createElement("button");
    b.className = "ws-dot" + (i === state.curWS ? " active" : "") + (state.wins.some(w => w.ws === i) ? " has" : "");
    b.title = "Desktop " + (i + 1);
    b.onclick = () => switchWS(i);
    p.append(b);
  }
}
document.getElementById("pager").oncontextmenu = e => { e.preventDefault(); openOverview(); };
