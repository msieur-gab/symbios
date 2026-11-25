// lockscreen.js — the screens shown in place of the desk: the lock screen with its code (the owner's phone allows this
// screen), and "out of reach" when the board stops answering. Used by gate.js when the page starts, and by the quick
// panel's lock (shell/lock.js), which shows it at once, without starting the page again, so the code appears as soon as
// the board gives it (Gab, 23 Nov: "There's latency when locking the screen before the code can appear").
const screen = document.getElementById("lockscreen");
export const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text || "" });
export const held = { now: false };  // this screen locked itself: what waits on the board (gate.js watch) stands down
const sleep = ms => new Promise(res => setTimeout(res, ms));

// a request that gives up: an unplugged cable can leave one hanging instead of failing
export async function within(url, ms, opts = {}) {
  const stop = new AbortController(), t = setTimeout(() => stop.abort(), ms);
  try { return await fetch(url, { ...opts, signal: stop.signal }); } catch { return null; } finally { clearTimeout(t); }
}

export function show(...nodes) {
  const inner = el("div", "lk-inner");
  inner.append(el("div", "lk-brand", "SYMBIOS"), ...nodes);
  screen.replaceChildren(inner);
  screen.hidden = false;
}

// the desk taken off the page: its windows, dock and islands, their sound and video stopped. What it showed isn't left
// behind the lock screen; it loads again, whole, once the screen is let back in
export function clearDesk() {
  for (const m of document.querySelectorAll("audio, video")) m.pause();
  for (const n of [...document.body.children]) if (n !== screen && n.tagName !== "SCRIPT") n.remove();
}

export function locked() {
  const code = el("div", "lk-code num"), said = el("div", "lk-said read");
  show(el("div", "lk-title", "This desk is locked"), code, said);
  (async () => {
    while (true) {
      const r = await within("/api/screen/ask", 15000, { method: "POST" });
      const ask = r?.ok ? await r.json().catch(() => null) : null;
      if (!ask) {
        code.textContent = ""; said.textContent = "The desk doesn’t answer. Trying again…";
        await sleep(5000);
        continue;
      }
      code.textContent = ask.code;
      said.textContent = "Open the companion on the owner’s phone: it shows this code. Allow this screen there.";
      const until = Date.now() + 290000; // a code holds 5 minutes; then a new one
      let state = "waiting";
      while (state === "waiting" && Date.now() < until) {
        try { ({ state } = await fetch("/api/screen/wait?id=" + encodeURIComponent(ask.id)).then(r => r.json())); }
        catch { await sleep(3000); }
      }
      if (state === "allowed") return location.reload(); // the pass is set: the desk itself loads
      if (state === "refused") { code.textContent = ""; said.textContent = "The owner’s phone refused this screen."; return; }
    }
  })();
}

// the board stopped answering (its cable pulled, or it left the WiFi): the desk locks, and starts again when the board
// is back, through the gate as any start: the cable's pass ends when it is unplugged, so the phone allows the screen
// again (Gab, 23 Nov: "when it's unplugged, the UI should lock")
export function outOfReach() {
  held.now = true;
  clearDesk();
  show(el("div", "lk-title", "The desk is out of reach"),
    el("div", "lk-said read", "Plug the board back in, or come back to its WiFi. The desk opens again from here."));
  (async () => {
    while (!(await within("/api/screen", 4000))?.ok) await sleep(3000);
    location.reload();
  })();
}
