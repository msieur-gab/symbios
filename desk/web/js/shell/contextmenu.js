// contextmenu.js (from SymbiOS v1, core/contextmenu.js) — the per-window context menu (right-click / touch long-press).
// One job: build + place + wire the popup. wm.js calls openCtx; everything else
// (which verbs exist, moving to a desktop) is handled here.
import { WORKSPACES } from './state.js';
import { toggleMin, toggleMax, closeWin, moveWinToWS } from './wm.js';

const ctx = document.getElementById('ctx');

export function openCtx(e, win){
  let html = `<div class="ctx-item" data-a="min">Minimize</div>
    <div class="ctx-item" data-a="max">${win.max?'Restore':'Maximize'}</div>
    <div class="ctx-sep"></div><div class="ctx-lbl">Move to desktop</div><div class="ctx-ws">`;
  for(let i=0;i<WORKSPACES;i++) html += `<button data-ws="${i}" class="${i===win.ws?'cur':''}">${i+1}</button>`;
  html += `</div><div class="ctx-sep"></div><div class="ctx-item" data-a="close">Close</div>`;
  ctx.innerHTML = html; ctx.classList.add('open');
  const x = Math.min(e.clientX, window.innerWidth-210), y = Math.min(e.clientY, window.innerHeight-260);
  ctx.style.left = x+'px'; ctx.style.top = y+'px';
  ctx.querySelectorAll('[data-a]').forEach(it => it.onclick = () => {
    const a = it.dataset.a;
    if(a==='min')   toggleMin(win, true);
    if(a==='max')   toggleMax(win);
    if(a==='close') closeWin(win);
    closeCtx();
  });
  ctx.querySelectorAll('[data-ws]').forEach(b => b.onclick = () => { moveWinToWS(win, +b.dataset.ws); closeCtx(); });
}

export function closeCtx(){ ctx.classList.remove('open'); }

document.addEventListener('pointerdown', e => { if(!ctx.contains(e.target)) closeCtx(); }, true);
