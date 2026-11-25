// lock.js — the quick panel's lock. Once the desk has an owner (gate.js), it is the real one: this screen's pass
// ends, and only the owner's phone lets it back in (the lock screen with its code). Before that (a laptop, a board
// with no owner), the desk is only hidden behind a screen with the time, and Escape unlocks, as v1's
// "esc — dev bypass" did.
const screen = document.getElementById("lockscreen");
let timer = null;

function paint() {
  const now = new Date();
  screen.querySelector(".lk-time").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  screen.querySelector(".lk-date").textContent = now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" });
}
let real = false;
export function phoneLock(on) { real = !!on; }

export async function lock() {
  if (real) {  // the lock screen at once, in place, its code asked straight away: no start of the page in between
    const { held, clearDesk, locked } = await import("../lockscreen.js");
    held.now = true;
    clearDesk();
    await fetch("/api/screen/lock", { method: "POST" }).catch(() => null);
    return locked();
  }
  screen.innerHTML = `<div class="lk-inner"><div class="lk-brand">SYMBIOS</div><div class="lk-time"></div><div class="lk-date"></div>
    <div class="lk-hint">Hidden. No phone owns this desk yet.<br>esc: unlock</div></div>`;
  paint();
  screen.hidden = false;
  clearInterval(timer);
  timer = setInterval(paint, 10000);
}
export function unlock() { screen.hidden = true; clearInterval(timer); }
document.addEventListener("keydown", e => { if (e.key === "Escape" && !screen.hidden) { e.stopImmediatePropagation(); unlock(); } }, true);
