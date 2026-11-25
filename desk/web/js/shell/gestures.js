// gestures.js (from SymbiOS v1, core/gestures.js) — the input layer: keyboard shortcuts, the mouse top-edge reveal,
// and touch gestures. One job: turn raw input into shell commands (switch
// desktop, open overview, move window). It never manipulates windows directly —
// it calls wm/workspaces/overview.
//
// Touch P1 fixes vs the v5 prototype:
//   B1 — touch had no reliable overview path: added the always-visible overview
//        button (wired in overview.js) + the swipe/2-finger gestures below.
//   B2 — wallpaper L/R swipe now keys off e.target===desktop (the literal
//        wallpaper) instead of "not inside a .win", so it can't be half-blocked.
//   B3 — 2-finger gesture state is reset on any non-2-touch start AND on
//        touchcancel, so a staggered finger-lift can't leave stale state.
import { state, WORKSPACES } from './state.js';
import { switchWS } from './workspaces.js';
import { openOverview, closeOverview, isOverviewOpen, hotHint } from './overview.js';
import { closeLauncher } from './launcher.js';
import { closeCtx } from './contextmenu.js';
import { abortDrag, moveWinToWS } from './wm.js';

const desktop  = document.getElementById('desktop');
const ov       = document.getElementById('ov');
const launcher = document.getElementById('launcher');

/* ── keyboard shortcuts ─────────────────────────────────────────────────── */
document.addEventListener('keydown', e => {
  const typing = ['INPUT','TEXTAREA'].includes(document.activeElement && document.activeElement.tagName);
  if(e.ctrlKey && !e.shiftKey && e.key>='1' && e.key<='4'){ e.preventDefault(); switchWS(+e.key-1); }
  if(e.ctrlKey && e.shiftKey && e.code>='Digit1' && e.code<='Digit4'){ e.preventDefault();
    const f = state.wins.find(w => w.el.classList.contains('focused')); if(f) moveWinToWS(f, +e.code.slice(-1)-1); }
  if(!typing && e.ctrlKey && e.key==='ArrowUp'){ e.preventDefault(); isOverviewOpen() ? closeOverview() : openOverview(); }
  if(e.key==='Escape'){ closeLauncher(); closeOverview(); closeCtx(); }
});

/* ── top-edge reveal (mouse hover): push to top ≤4px, dwell ~170ms → overview ─ */
const HOT_BAND = 4, HOT_DWELL = 170;
let hotTimer = null;
function clearHot(){ if(hotTimer){ clearTimeout(hotTimer); hotTimer=null; } hotHint.classList.remove('peek'); }
document.addEventListener('pointermove', e => {
  if(e.pointerType==='touch') return;
  const busy = state.dragState || state.ovDrag || state.hotCooldown
    || ov.classList.contains('open') || launcher.classList.contains('open');
  if(busy){ clearHot(); return; }
  if(e.clientY <= HOT_BAND){
    hotHint.classList.add('peek');
    if(!hotTimer) hotTimer = setTimeout(() => { hotTimer=null; openOverview(); }, HOT_DWELL);
  } else clearHot();
});

/* ── touch gestures ─────────────────────────────────────────────────────────
   Meaning is set by ORIGIN + finger count, so they never fight a window drag:
   1 finger on a window is always a move/scroll (handled in wm.js).
     · 1 finger from the top strip, swipe down  -> overview
     · 1 finger on the wallpaper,  swipe L/R     -> change desktop
     · 2 fingers anywhere: down -> overview, L/R -> change desktop          */
const SWIPE = 60;

let tg = null;
const tgEnd = () => { tg = null; };
document.addEventListener('pointerdown', e => {
  if(e.pointerType!=='touch' || isOverviewOpen()) return;
  tg = { x:e.clientX, y:e.clientY,
    fromTop: e.clientY <= 24,
    onWin:  !!e.target.closest('.win'),
    onWall: e.target === desktop,          // B2: precise wallpaper test
    fired: false };
}, true);
document.addEventListener('pointermove', e => {
  if(!tg || tg.fired || e.pointerType!=='touch') return;
  const dx=e.clientX-tg.x, dy=e.clientY-tg.y, ax=Math.abs(dx), ay=Math.abs(dy);
  if(dy>SWIPE && ay>ax*1.3 && tg.fromTop && !tg.onWin){ openOverview(); tg.fired=true; return; }  // down from top
  if(ax>SWIPE && ax>ay*1.4 && tg.onWall){                                                          // L/R on wallpaper
    dx<0 ? switchWS(Math.min(WORKSPACES-1, state.curWS+1)) : switchWS(Math.max(0, state.curWS-1));
    tg.fired = true;
  }
});
document.addEventListener('pointerup', tgEnd);
document.addEventListener('pointercancel', tgEnd);

/* 2-finger swipe anywhere — works when the desktop is full of windows and
   there's no wallpaper to grab. abortDrag() cancels any stray single-pointer
   move a titlebar touch may have started. */
let tg2 = null;
const mid = ts => ({ x:(ts[0].clientX+ts[1].clientX)/2, y:(ts[0].clientY+ts[1].clientY)/2 });
const clearTg2 = () => { tg2 = null; };
document.addEventListener('touchstart', e => {
  if(e.touches.length===2){ const m = mid(e.touches); tg2 = { x:m.x, y:m.y, fired:false }; }
  else tg2 = null;                                  // B3: any non-2 touch drops stale state
}, { passive:true });
document.addEventListener('touchmove', e => {
  if(!tg2 || tg2.fired || e.touches.length<2) return;
  const m = mid(e.touches), dx=m.x-tg2.x, dy=m.y-tg2.y, ax=Math.abs(dx), ay=Math.abs(dy);
  if(ax<SWIPE && ay<SWIPE) return;
  abortDrag();
  if(ay>ax){ if(dy>0 && !isOverviewOpen()) openOverview(); }
  else dx<0 ? switchWS(Math.min(WORKSPACES-1, state.curWS+1)) : switchWS(Math.max(0, state.curWS-1));
  tg2.fired = true;
}, { passive:true });
document.addEventListener('touchend', e => { if(e.touches.length<2) clearTg2(); }, { passive:true });
document.addEventListener('touchcancel', clearTg2, { passive:true });   // B3

/* ── the touchpad's sideways swipe: the desktops, never the browser's back and forward ─────────────────
   Gab, 23 Nov: "I get so much used to my operating system doing swipe left and right to navigate between
   different desks that I've been reloading the window". Brave reads a two-finger swipe as back/forward;
   overscroll-behavior-x (components.css) stops that, and here the swipe moves one desktop, like his OS.
   Content that scrolls sideways under the pointer (a wide table, the dock's tiles) keeps the swipe. */
const SWIPE_PX = 140;        // how far the fingers travel for one desktop
const GESTURE_GAP = 220;     // ms without movement: the swipe has ended
let swipe = { dx: 0, done: false, timer: null };
function scrollsSideways(el) {
  for (; el && el !== document.body; el = el.parentElement) {
    if (el.scrollWidth > el.clientWidth + 1 && /(auto|scroll)/.test(getComputedStyle(el).overflowX)) return true;
  }
  return false;
}
document.addEventListener('wheel', e => {
  if(Math.abs(e.deltaX) <= Math.abs(e.deltaY) * 1.2 || e.ctrlKey) return;   // up/down scrolling and pinch stay as they are
  if(scrollsSideways(e.target)) return;
  e.preventDefault();
  clearTimeout(swipe.timer);
  swipe.timer = setTimeout(() => { swipe = { dx: 0, done: false, timer: null }; }, GESTURE_GAP);
  if(swipe.done || isOverviewOpen()) return;        // one desktop per swipe, however long it is
  swipe.dx += e.deltaX;
  if(Math.abs(swipe.dx) >= SWIPE_PX){
    switchWS(swipe.dx > 0 ? Math.min(WORKSPACES-1, state.curWS+1) : Math.max(0, state.curWS-1));
    swipe.done = true;
  }
}, { passive: false });

// and if a back/forward still gets through (a mouse's side buttons, Alt+←), the desk stays where it is
history.replaceState({ desk: true }, '');
history.pushState({ desk: true }, '');
addEventListener('popstate', () => history.pushState({ desk: true }, ''));
