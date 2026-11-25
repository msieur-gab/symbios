// state.js — the shell's shared state and work area. From SymbiOS v1 (app/desktop/js/core/state.js).
export const WORKSPACES = 4;

export const state = {
  wins: [],           // open windows: { id, appId, el, app, ws, x, y, w, h, min, max, snapped, prev, prevSnap, ac }
  curWS: 0,           // the desktop in front
  zTop: 10,
  winSeq: 0,
  dragState: null,
  ovDrag: null,
  hotCooldown: false,
  dockAuto: false,
  dockHidden: false,
};

export const desktop = document.getElementById("desktop");

let reserve = null;
export function getReserve() {
  if (state.dockAuto) return 16;
  if (reserve === null) reserve = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--dock-reserve")) || 92;
  return reserve;
}
export function invalidateReserve() { reserve = null; }
export const workArea = () => ({ w: innerWidth, h: innerHeight - getReserve() });
