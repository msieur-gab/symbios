// overview.js (from SymbiOS v1, core/overview.js; each window shown by its own title) — the multi-desktop preview (representational thumbnails) + drag a
// window between desktops. One job: build/open/close the overview and own its
// triggers (backdrop click, the dock overview button). Keyboard/touch entry
// points live in gestures.js and call openOverview().
import { state, WORKSPACES, workArea } from './state.js';
import { APPS } from './loader.js';
import { switchWS } from './workspaces.js';
import { moveWinToWS } from './wm.js';

const ov = document.getElementById('ov'), ovRow = document.getElementById('ov-row');
export const hotHint = document.getElementById('hot-hint');

export function isOverviewOpen(){ return ov.classList.contains('open'); }
export function openOverview(){ buildOverview(); ov.classList.add('open'); hotHint.classList.remove('peek'); }
export function closeOverview(){
  ov.classList.remove('open');
  state.hotCooldown = true;                    // stop the top-edge reveal re-firing on the way up
  setTimeout(() => state.hotCooldown = false, 650);
}

function buildOverview(){
  ovRow.innerHTML = ''; const wa = workArea();
  for(let i=0;i<WORKSPACES;i++){
    const pane = document.createElement('div');
    pane.className = 'ov-pane' + (i===state.curWS?' cur':''); pane.dataset.ws = i;
    const stage = document.createElement('div'); stage.className = 'ov-stage';
    const dWins = state.wins.filter(w => w.ws===i && !w.min);
    if(!dWins.length){ const e = document.createElement('div'); e.className='ov-empty'; e.textContent='No windows'; stage.appendChild(e); }
    // scale needs the stage width — set after layout via rAF
    requestAnimationFrame(() => {
      const sw = stage.clientWidth, sh = stage.clientHeight, sx = sw/wa.w, sy = sh/wa.h;
      dWins.sort((a,b)=>(+a.el.style.zIndex||0)-(+b.el.style.zIndex||0)).forEach(w => {
        const m = document.createElement('div'); m.className = 'ov-win';
        m.style.left = Math.max(0, w.x*sx)+'px'; m.style.top = Math.max(0, w.y*sy)+'px';
        m.style.width = Math.max(34, w.w*sx)+'px'; m.style.height = Math.max(24, w.h*sy)+'px';
        m.innerHTML = `<div class="ov-win-head"></div>
          <div class="ov-win-body"><span class="gl">${APPS[w.appId].icon}</span><span></span></div>`;
        m.querySelector('.ov-win-body span:last-child').textContent = w.el.querySelector('.win-title span').textContent;
        m.addEventListener('pointerdown', ev => startOvDrag(ev, w, m));
        stage.appendChild(m);
      });
    });
    pane.appendChild(stage);
    const lbl = document.createElement('div'); lbl.className='ov-label'; lbl.textContent='Desktop '+(i+1); pane.appendChild(lbl);
    pane.addEventListener('click', () => { if(state.ovDrag) return; switchWS(i); closeOverview(); });
    ovRow.appendChild(pane);
  }
}

function startOvDrag(e, win, el){
  e.stopPropagation();
  const r = el.getBoundingClientRect();
  state.ovDrag = { win, el, dx:e.clientX-r.left, dy:e.clientY-r.top, moved:false, w:r.width, h:r.height };
  try { el.setPointerCapture(e.pointerId); } catch(_){}
  el.addEventListener('pointermove', ovMove);
  el.addEventListener('pointerup', ovUp);
  el.addEventListener('pointercancel', ovCancel);
}
// a hijacked/cancelled touch must not leave a thumbnail stuck mid-drag
function ovCancel(e){
  const d = state.ovDrag; if(!d) return;
  try { d.el.releasePointerCapture(e.pointerId); } catch(_){}
  d.el.removeEventListener('pointermove', ovMove);
  d.el.removeEventListener('pointerup', ovUp);
  d.el.removeEventListener('pointercancel', ovCancel);
  state.ovDrag = null;
  buildOverview();
}
function ovMove(e){
  const d = state.ovDrag; if(!d) return;
  if(!d.moved){ d.moved=true; d.el.classList.add('drag'); d.el.style.position='fixed'; d.el.style.width=d.w+'px'; d.el.style.height=d.h+'px'; }
  d.el.style.left = (e.clientX-d.dx)+'px'; d.el.style.top = (e.clientY-d.dy)+'px';
  const pane = document.elementFromPoint(e.clientX, e.clientY)?.closest('.ov-pane');
  document.querySelectorAll('.ov-pane').forEach(p => p.classList.toggle('drop', p===pane));
}
function ovUp(e){
  const d = state.ovDrag; if(!d) return;
  try { d.el.releasePointerCapture(e.pointerId); } catch(_){}
  d.el.removeEventListener('pointermove', ovMove); d.el.removeEventListener('pointerup', ovUp);
  d.el.removeEventListener('pointercancel', ovCancel);
  if(d.moved){
    const pane = document.elementFromPoint(e.clientX, e.clientY)?.closest('.ov-pane');
    if(pane){ const ws = +pane.dataset.ws; if(ws !== d.win.ws) moveWinToWS(d.win, ws); }
    setTimeout(() => { state.ovDrag = null; buildOverview(); }, 0);
  } else { state.ovDrag = null; }
}

ov.addEventListener('pointerdown', e => { if(e.target===ov || e.target===ovRow) closeOverview(); });
// B1: an always-visible overview button gives touch (and mouse) a one-tap path
document.getElementById('overview-btn')?.addEventListener('click', openOverview);
