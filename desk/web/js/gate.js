// gate.js — what the desk's page runs first (the old page's lock.js, brought into the new desk at the fold). Once
// the desk has an owner, a screen showing it (the board's own HDMI kiosk, a laptop on the cable or the WiFi) is let in
// only after the owner's phone allows it (SECURE-LINK.md, step 5): until then the lock screen shows a code, the
// phone's companion shows the same code with Allow and Refuse, and the desk itself (main.js) isn't even loaded, so
// nothing of it asks the server meanwhile. Let in, the screen waits on the desk (/api/screen/watch): when the phone
// disconnects it, or the desk gets an owner meanwhile, it goes back to the lock screen. The quick panel's lock ends
// this screen's pass, like locking a computer (shell/lock.js). Near the board with no owner yet, a card shows the QR
// code a phone claims the desk with (Gab, 23 Nov: "the phone that scanned the QR code is the one that claimed the board").
// The lock screen itself, and "out of reach", live in lockscreen.js, which the quick panel's lock uses too.
import { initTheme } from "./shared/theme.js";
import { el, show, locked, held, within, outOfReach } from "./lockscreen.js";

initTheme();
const asked = await fetch("/api/screen").then(r => r.ok ? r.json() : null).catch(() => null);
if (!asked) await import("./main.js"); // a server with no lock (the laptop's next/)
else if (!asked.claimed) asked.allowed ? claiming() : unowned();
else if (asked.allowed) {
  await import("./main.js"); // let in by the owner's phone
  (await import("./shell/lock.js")).phoneLock(true);
  watch();
} else locked();

// no owner yet, and this screen isn't the board's own or on its cable: no phone can allow it
function unowned() {
  show(el("div", "lk-title", "This desk has no owner yet"),
    el("div", "lk-said read", "Open it on a computer plugged into the board’s USB cable: it shows a QR code. Scan it with your phone to install the companion and claim the desk. Then allow this screen from the phone."));
}

// let in: the desk answers as soon as this screen's pass ends (or after 10 s, and the screen asks again). A board that
// stops answering (unplugged, or off the WiFi) locks the screen (lockscreen.js outOfReach)
async function watch() {
  const { phoneLock } = await import("./shell/lock.js");
  while (true) {
    const r = await within("/api/screen/watch", 15000);  // the board answers within 10 s
    if (held.now) return; // this screen locked itself meanwhile: the lock screen is up already
    if (r?.status === 403) return location.reload(); // the pass was gone before it even asked
    const now = r?.ok ? await r.json().catch(() => null) : null;
    if (now && (!now.allowed || !now.claimed)) return location.reload(); // its pass ended, or the desk was released: the QR card
    if (now) { phoneLock(now.claimed); continue; }
    // no answer: asked again at once, briefly; still none, the screen locks (at most ~20 s after the cable is pulled,
    // usually a few: the browser drops what waits when the cable's network goes)
    await new Promise(res => setTimeout(res, 1000));
    if (!(await within("/api/screen", 4000))?.ok && !held.now) return outOfReach();
  }
}

// no owner yet, near the board (its own screen, or a computer on its cable): the desk itself isn't loaded; the screen
// holds still on the claim card, in its centre, until a phone claims the desk, then starts again into the lock screen,
// for the owner's phone to allow it (Gab, 23 Nov: "Rather than displaying the UI, we should have a screen which is
// freezed and the card should be in the center of the screen"). The QR code holds a few minutes and opens once, so
// the card asks for the current one again before it ends.
function claiming() {
  const qr = el("div", "claim-qr"), code = el("div", "claim-code num"), said = el("div", "lk-said read");
  qr.hidden = true;  // until its code arrives: an empty white box otherwise
  show(el("div", "lk-title", "This desk has no owner yet"), qr, code, said);
  const fill = async () => {
    const got = await fetch("/api/trust/code").then(r => r.ok ? r.json() : null).catch(() => null);
    if (!got) return setTimeout(fill, 5000); // out of reach a moment (an owner meanwhile: the check below starts again)
    qr.innerHTML = got.qr || "";
    qr.hidden = !got.qr;
    code.textContent = got.code.slice(0, 4) + "-" + got.code.slice(4);
    // the network named, so nobody has to work out which one (Gab, 23 Nov: "we could perhaps give the name of the Wi-Fi")
    const on = got.wifi ? "on the WiFi \u201c" + got.wifi + "\u201d" : "on the same WiFi";
    said.textContent = !got.desk ? "The desk is on no WiFi yet: give it one first, so the phone can reach it."
      : got.qr ? "Scan it with your phone, " + on + ": it opens the companion, to install it and claim this desk."
      : "Open the companion on your phone, " + on + ", and type this code to claim the desk at " + got.desk + ".";
    setTimeout(fill, Math.max(5, got.left - 20) * 1000); // the next code just before this one ends
  };
  fill();
  setInterval(async () => {
    const now = await fetch("/api/screen").then(r => r.ok ? r.json() : null).catch(() => null);
    if (now?.claimed) location.reload();
  }, 3000);
}
