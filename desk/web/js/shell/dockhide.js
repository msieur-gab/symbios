// dockhide.js (from SymbiOS v1, core/dockhide.js) — dock auto-hide (macOS / Zorin / ChromeOS style). One job: slide
// the three dock islands off the bottom and reveal them when the pointer hits
// the bottom edge. The dock OVERLAYS windows on reveal (state.js shrinks the
// reserve when dockAuto is on, so windows already use the bottom space — nothing
// resizes on reveal/hide, only on toggle).
//
// Mouse: touch the very bottom edge to reveal; move up out of the dock band to
// hide. Touch: swipe up from the bottom edge to reveal; tap a window to hide.
// Stays revealed while a dock panel (quick-settings / launcher / mini-player /
// context menu / overview) is open or a window is being dragged.
import { state } from './state.js';
import { fitMaximized } from './wm.js';

const KEY = 'next.dockAuto';
const REVEAL = 48;    // px from the bottom edge that triggers a reveal. Kept well
                      // above the host OS's own edge trigger (a few px) so summoning
                      // our dock never fights the host taskbar/menu. Trade-off:
                      // larger = easier to summon, but more eager near window bottoms.
const ZONE   = 100;   // keep revealed while the pointer is within this bottom band (>= REVEAL)
const HIDE_DELAY = 420;
let hideTimer = null;

function panelsOpen(){
  return ['qs','launcher','ov'].some(id => document.getElementById(id)?.classList.contains('open'))
    || document.getElementById('ctx')?.classList.contains('open')
    || !!state.dragState;
}

function show(){
  if(hideTimer){ clearTimeout(hideTimer); hideTimer = null; }
  if(state.dockHidden){ document.body.classList.remove('dock-hidden'); state.dockHidden = false; }
}
function hideNow(){
  if(!state.dockAuto || panelsOpen()) return;
  if(!state.dockHidden){ document.body.classList.add('dock-hidden'); state.dockHidden = true; }
}
function scheduleHide(){
  if(!state.dockAuto || hideTimer || panelsOpen()) return;
  hideTimer = setTimeout(() => { hideTimer = null; hideNow(); }, HIDE_DELAY);
}

// mouse: edge reveal, leave-to-hide
document.addEventListener('pointermove', e => {
  if(!state.dockAuto || e.pointerType === 'touch') return;
  const h = window.innerHeight;
  if(state.dockHidden){
    if(e.clientY >= h - REVEAL) show();
  } else {
    if(e.clientY >= h - ZONE || e.target.closest('.island')) show();
    else scheduleHide();
  }
});

// touch: swipe up from the bottom edge reveals; tapping a window hides
let tStart = null;
document.addEventListener('pointerdown', e => {
  if(!state.dockAuto || e.pointerType !== 'touch') return;
  if(e.clientY >= window.innerHeight - REVEAL) tStart = { y: e.clientY };
  else if(!state.dockHidden && !e.target.closest('.island')) scheduleHide();
}, true);
document.addEventListener('pointermove', e => {
  if(!tStart || e.pointerType !== 'touch') return;
  if(tStart.y - e.clientY > 40){ show(); tStart = null; }
});
document.addEventListener('pointerup', () => { tStart = null; });

// keep revealed while interacting, re-evaluate when a panel closes
window.addEventListener('blur', () => { if(state.dockAuto) scheduleHide(); });

/* ── public API (Settings toggle + boot) ─────────────────────────────────── */
export function dockAutoEnabled(){ return state.dockAuto; }
export function setDockAuto(on){
  state.dockAuto = on;
  try { localStorage.setItem(KEY, on ? '1' : '0'); } catch(_){}
  on ? hideNow() : show();
  fitMaximized();            // reserve changed → refit any maximized windows
}
export function initDock(){
  let on = false;   // dock shown by default; the user opts into auto-hide in Settings → Dock
  const q = new URLSearchParams(location.search).get('dock');   // ?dock=off|on for previewing
  if(q === 'off' || q === 'pin') on = false;
  else if(q === 'on' || q === 'auto') on = true;
  else { try { const v = localStorage.getItem(KEY); if(v !== null) on = v === '1'; } catch(_){} }
  state.dockAuto = on;
  if(on){ document.body.classList.add('dock-hidden'); state.dockHidden = true; }
}
