// wm.js — the window manager: open, focus, close, minimise, maximise, drag, snap to the screen's edges
// (sides → halves, side corners → quarters), resize from every edge. From SymbiOS v1
// (app/desktop/js/core/wm.js), changed for a desk of files: an app may have several windows, each window
// holds one file or folder (its key), and its title follows what it shows.
import { state, desktop, workArea, getReserve } from "./state.js";
import { APPS } from "./loader.js";
import { I } from "../shared/icons.js";
import { openCtx } from "./contextmenu.js";
import { renderDock } from "./dock.js";
import { renderPager, applyWorkspace } from "./workspaces.js";
import { closeLauncher } from "./launcher.js";

const snapPrev = document.getElementById("snap-prev");

/* ── lifecycle ── */

// open an app on a file or folder ({path, kind…}); a window already showing it comes forward instead
export function launch(appId, item, among) {
  const app = APPS[appId];
  if (!app) return;
  const key = item?.path ?? "";
  const existing = app.many ? state.wins.find(w => w.appId === appId && w.el.dataset.key === key)
    : state.wins.find(w => w.appId === appId);
  if (existing) {
    if (existing.ws !== state.curWS) { existing.ws = state.curWS; applyWorkspace(); }
    if (existing.min) toggleMin(existing, false);
    if (!app.many && item) existing.app.show?.(item, among);
    focusWin(existing);
    closeLauncher();
    return existing;
  }
  const wa = workArea();
  const w = Math.min(app.size[0], wa.w - 40), h = Math.min(app.size[1], wa.h - 40);
  const n = state.wins.filter(x => x.ws === state.curWS).length % 6;  // a gentle cascade
  const x = Math.max(20, (wa.w - w) / 2 + n * 26 - 60), y = Math.max(20, (wa.h - h) / 2 + n * 22 - 40);
  const el = document.createElement("div");
  el.className = "win";
  el.dataset.app = appId;
  el.dataset.key = key;
  el.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px;`;
  el.innerHTML = `<div class="win-head"><div class="win-title">${app.icon}<span></span></div>
    <div class="win-ctrl"><button class="win-btn min" title="Minimise">${I.min}</button>
    <button class="win-btn maxb" title="Maximise">${I.max}</button>
    <button class="win-btn close" title="Close">${I.close}</button></div></div>
    <div class="win-body"></div>
    <div class="rs rs-n" data-d="n"></div><div class="rs rs-s" data-d="s"></div>
    <div class="rs rs-e" data-d="e"></div><div class="rs rs-w" data-d="w"></div>
    <div class="rs rs-ne" data-d="ne"></div><div class="rs rs-nw" data-d="nw"></div>
    <div class="rs rs-se" data-d="se"></div><div class="rs rs-sw" data-d="sw"></div>`;
  el.querySelector(".win-title span").textContent = item?.name || app.name;
  desktop.append(el);

  const win = { id: "w" + ++state.winSeq, appId, el, ws: state.curWS, x, y, w, h,
    min: false, max: false, snapped: null, prev: null, prevSnap: null, ac: new AbortController() };
  state.wins.push(win);
  const sig = { signal: win.ac.signal };
  el.addEventListener("pointerdown", () => focusWin(win), { capture: true, signal: win.ac.signal });
  const head = el.querySelector(".win-head");
  head.addEventListener("pointerdown", e => startDrag(e, win, head), sig);
  head.addEventListener("dblclick", e => { if (!e.target.closest(".win-btn")) toggleMax(win); }, sig);
  head.addEventListener("contextmenu", e => { e.preventDefault(); openCtx(e, win); }, sig);
  el.querySelector(".min").addEventListener("click", e => { e.stopPropagation(); toggleMin(win, true); }, sig);
  el.querySelector(".maxb").addEventListener("click", e => { e.stopPropagation(); toggleMax(win); }, sig);
  el.querySelector(".close").addEventListener("click", e => { e.stopPropagation(); closeWin(win); }, sig);
  el.querySelectorAll(".rs").forEach(h => h.addEventListener("pointerdown", e => startResize(e, win, h.dataset.d), sig));
  try { win.app = app.render(el.querySelector(".win-body"), item, among); }
  catch (e) { console.error(appId + ": " + e.message); }  // the window stays, and can be closed

  focusWin(win);
  renderPager();
  closeLauncher();
  return win;
}

// what a window shows changed: its title, and the file or folder it holds
export function retitle(inside, title, key) {
  const el = inside.closest(".win");
  if (!el) return;
  el.querySelector(".win-title span").textContent = title;
  if (key != null) el.dataset.key = key;
  renderDock();
}

// a window over the whole screen, above the dock (an app asks: shared/desk.js fullScreen); the dock steps aside while one is
export function fullScreen(inside, on) {
  inside.closest(".win")?.classList.toggle("full-screen", on);
  document.body.classList.toggle("full-screen", !!desktop.querySelector(".win.full-screen"));
}

export function focusWin(win) {
  if (+win.el.style.zIndex !== state.zTop) win.el.style.zIndex = ++state.zTop;
  state.wins.forEach(w => w.el.classList.toggle("focused", w === win));
  renderDock();
}

export function closeWin(win) {
  try { win.app?.closing?.(); } catch { /* closing anyway */ }
  win.ac.abort();
  win.el.classList.add("minimizing");
  setTimeout(() => win.el.remove(), 150);
  state.wins.splice(state.wins.indexOf(win), 1);
  const next = state.wins.filter(w => w.ws === state.curWS && !w.min).sort((a, b) => b.el.style.zIndex - a.el.style.zIndex)[0];
  next ? focusWin(next) : renderDock();
  renderPager();
}

export function toggleMin(win, force) {
  win.min = force !== undefined ? force : !win.min;
  win.el.style.display = win.min || win.ws !== state.curWS ? "none" : "flex";
  if (!win.min) focusWin(win);
  renderDock();
  renderPager();
}

export function toggleMax(win) {
  win.snapped = null;
  if (win.max) {
    win.max = false;
    win.el.classList.remove("maxed");
    Object.assign(win.el.style, { left: win.prev.x + "px", top: win.prev.y + "px", width: win.prev.w + "px", height: win.prev.h + "px" });
    Object.assign(win, win.prev);
  } else {
    win.prev = { x: win.x, y: win.y, w: win.w, h: win.h };
    win.max = true;
    win.el.classList.add("maxed");
    const wa = workArea();
    Object.assign(win.el.style, { left: "8px", top: "8px", width: wa.w - 16 + "px", height: wa.h - 8 + "px" });
  }
  focusWin(win);
}

export function moveWinToWS(win, ws) { win.ws = ws; applyWorkspace(); renderPager(); }

export function fitMaximized() {
  const wa = workArea();
  state.wins.forEach(w => { if (w.max) Object.assign(w.el.style, { left: "8px", top: "8px", width: wa.w - 16 + "px", height: wa.h - 8 + "px" }); });
}

/* ── dragging (a long press on touch = the window's menu; a live preview of the snap) ── */

export function startDrag(e, win, head) {
  if (e.target.closest(".win-btn")) return;
  focusWin(win);
  if (win.max || win.snapped) {  // grabbing a maximised or snapped window lets it go under the pointer
    const p = win.prevSnap || { w: Math.min(win.w, 640), h: Math.min(win.h, 440) };
    win.max = false; win.el.classList.remove("maxed"); win.snapped = null; win.prevSnap = null;
    win.w = p.w; win.h = p.h; win.x = e.clientX - win.w / 2; win.y = e.clientY - 20;
    Object.assign(win.el.style, { width: win.w + "px", height: win.h + "px", left: win.x + "px", top: win.y + "px" });
  }
  const r = win.el.getBoundingClientRect();
  state.dragState = { win, dx: e.clientX - r.left, dy: e.clientY - r.top, sx: e.clientX, sy: e.clientY, zone: null, lp: null, head };
  if (e.pointerType === "touch") state.dragState.lp = setTimeout(() => { openCtx({ clientX: state.dragState.sx, clientY: state.dragState.sy }, win); abortDrag(); }, 500);
  try { head.setPointerCapture(e.pointerId); } catch { /* fine */ }
  head.addEventListener("pointermove", onDrag);
  head.addEventListener("pointerup", endDrag);
}

function onDrag(e) {
  const d = state.dragState;
  if (!d) return;
  const { win, dx, dy } = d, wa = workArea();
  if (d.lp && (Math.abs(e.clientX - d.sx) > 8 || Math.abs(e.clientY - d.sy) > 8)) { clearTimeout(d.lp); d.lp = null; }
  const x = Math.max(-(win.w - 120), Math.min(e.clientX - dx, wa.w - 120));
  const y = Math.max(0, Math.min(e.clientY - dy, wa.h - 40));
  win.x = x; win.y = y; win.el.style.left = x + "px"; win.el.style.top = y + "px";
  const z = zoneFor(e.clientX, e.clientY);
  d.zone = z;
  z ? showSnap(z) : hideSnap();
}

function endDrag(e) {
  const d = state.dragState;
  if (!d) return;
  try { d.head.releasePointerCapture(e.pointerId); } catch { /* fine */ }
  d.head.removeEventListener("pointermove", onDrag);
  d.head.removeEventListener("pointerup", endDrag);
  if (d.lp) clearTimeout(d.lp);
  state.dragState = null;
  hideSnap();
  if (d.zone) applySnap(d.win, d.zone);
}

export function abortDrag() {
  const d = state.dragState;
  if (!d) return;
  d.head.removeEventListener("pointermove", onDrag);
  d.head.removeEventListener("pointerup", endDrag);
  if (d.lp) clearTimeout(d.lp);
  state.dragState = null;
  hideSnap();
}

/* ── snapping: the sides make halves, the side corners quarters; the top stays free for the overview ── */

function snapRect(zone) {
  const g = 8, W = innerWidth, Hw = innerHeight - getReserve();
  const halfW = (W - 3 * g) / 2, halfH = (Hw - 3 * g) / 2, right = 2 * g + halfW, bottom = 2 * g + halfH;
  return { left: { x: g, y: g, w: halfW, h: Hw - g }, right: { x: right, y: g, w: halfW, h: Hw - g },
    tl: { x: g, y: g, w: halfW, h: halfH }, tr: { x: right, y: g, w: halfW, h: halfH },
    bl: { x: g, y: bottom, w: halfW, h: halfH }, br: { x: right, y: bottom, w: halfW, h: halfH } }[zone];
}
function zoneFor(cx, cy) {
  const W = innerWidth, H = innerHeight, E = 12, res = getReserve();
  const left = cx <= E, right = cx >= W - E;
  if (!left && !right) return null;
  const C = Math.max(140, Math.min(300, (H - res) * 0.34));
  const topB = cy <= C, botB = cy >= H - res - C;
  if (left) return topB ? "tl" : botB ? "bl" : "left";
  return topB ? "tr" : botB ? "br" : "right";
}
function showSnap(zone) {
  const r = snapRect(zone);
  Object.assign(snapPrev.style, { display: "block", left: r.x + "px", top: r.y + "px", width: r.w + "px", height: r.h + "px" });
}
function hideSnap() { snapPrev.style.display = "none"; }
function applySnap(win, zone) {
  if (!win.prevSnap) win.prevSnap = { x: win.x, y: win.y, w: win.w, h: win.h };
  win.max = false;
  win.el.classList.remove("maxed");
  const r = snapRect(zone);
  Object.assign(win, { x: r.x, y: r.y, w: r.w, h: r.h });
  Object.assign(win.el.style, { left: r.x + "px", top: r.y + "px", width: r.w + "px", height: r.h + "px" });
  win.snapped = zone;
  focusWin(win);
}

/* ── resizing ── */

export function startResize(e, win, dir) {
  if (win.max) return;
  e.stopPropagation();
  focusWin(win);
  win.snapped = null; win.prevSnap = null;
  const s = { x: e.clientX, y: e.clientY, w: win.w, h: win.h, l: win.x, t: win.y };
  const hd = e.currentTarget;
  try { hd.setPointerCapture(e.pointerId); } catch { /* fine */ }
  const MW = 240, MH = 160;
  function mv(ev) {
    const ddx = ev.clientX - s.x, ddy = ev.clientY - s.y;
    let { w, h, l, t } = s;
    if (dir.includes("e")) w = s.w + ddx;
    if (dir.includes("s")) h = s.h + ddy;
    if (dir.includes("w")) { w = s.w - ddx; l = s.l + ddx; }
    if (dir.includes("n")) { h = s.h - ddy; t = s.t + ddy; }
    if (w < MW) { if (dir.includes("w")) l = s.l + s.w - MW; w = MW; }
    if (h < MH) { if (dir.includes("n")) t = s.t + s.h - MH; h = MH; }
    Object.assign(win, { w, h, x: l, y: t });
    Object.assign(win.el.style, { width: w + "px", height: h + "px", left: l + "px", top: t + "px" });
  }
  function up(ev) {
    try { hd.releasePointerCapture(ev.pointerId); } catch { /* fine */ }
    hd.removeEventListener("pointermove", mv);
    hd.removeEventListener("pointerup", up);
  }
  hd.addEventListener("pointermove", mv);
  hd.addEventListener("pointerup", up);
}
