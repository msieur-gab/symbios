// What the desk's page runs first. Once the desk has an owner, a screen showing it (the board's own HDMI kiosk, a
// laptop on the cable or the WiFi) is let in only after the owner's phone allows it (the desk's SECURE-LINK.md,
// step 5): until then this lock screen shows a code, the phone's companion shows the same code with Allow and
// Refuse, and the desk itself (main.js) isn't even loaded, so nothing of it asks the server meanwhile.
// Let in, the screen waits on the desk (/api/screen/watch): when the phone disconnects it, or the desk gets an owner
// meanwhile, the desk answers at once and the screen goes back to the lock screen. The dock's Lock button ends this screen's pass itself, like locking a computer.
import { initTheme } from "./theme.js";

initTheme();
const asked = await fetch("/api/screen").then(r => r.json()).catch(() => null);
if (!asked || asked.allowed) {
  await import("./main.js"); // no owner yet, or let in already (or a desk too old to say)
  if (asked) watch(asked.claimed);
  if (asked && !asked.claimed) claimCard(); // near the board with no owner: the QR code a phone claims it with
} else if (!asked.claimed) unowned();
else lock();

// no owner yet, and this screen isn't the board's own or on its cable: nothing to ask for, since no phone can allow it
function unowned() {
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:var(--bg);color:var(--fg);text-align:center;padding:24px";
  const title = Object.assign(document.createElement("div"), { textContent: "This desk has no owner yet" });
  title.style.cssText = "font-size:22px";
  const said = Object.assign(document.createElement("div"), { textContent: "Open it on a computer plugged into the board's USB cable: it shows a QR code. Scan it with your phone to install the companion and claim the desk. Then allow this screen from the phone." });
  said.style.cssText = "color:var(--fg);font-size:15px;max-width:30em;line-height:1.5";
  box.append(title, said);
  document.body.replaceChildren(box);
}

function watch(claimed) {
  const button = document.getElementById("lock-btn");
  button.hidden = !claimed;
  button.onclick = async () => {
    await fetch("/api/screen/lock", { method: "POST" }).catch(() => null);
    location.reload();
  };
  (async () => {  // the desk answers as soon as this screen's pass ends (or after 25 s, and the screen asks again)
    while (true) {
      const r = await fetch("/api/screen/watch").catch(() => null);
      if (r?.status === 403) return location.reload(); // the pass was gone before it even asked
      const now = r?.ok ? await r.json().catch(() => null) : null;
      if (now && !now.allowed) return location.reload();
      if (now) button.hidden = !now.claimed;
      else await new Promise(res => setTimeout(res, 5000)); // out of reach: stays as it is, asks again
    }
  })();
}

function lock() {
  const box = document.createElement("div");
  box.style.cssText = "position:fixed;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;background:var(--bg);color:var(--fg);text-align:center;padding:24px";
  const title = Object.assign(document.createElement("div"), { textContent: "This desk is locked" });
  title.style.cssText = "font-size:22px";
  const code = document.createElement("div");
  code.style.cssText = "font-size:72px;letter-spacing:.25em;color:var(--accent);min-height:1.2em";
  const said = document.createElement("div");
  said.style.cssText = "color:var(--fg);font-size:15px;max-width:30em;line-height:1.5";
  box.append(title, code, said);
  document.body.replaceChildren(box);

  (async () => {
    while (true) {
      let ask;
      try { ask = await fetch("/api/screen/ask", { method: "POST" }).then(r => r.json()); } catch {
        code.textContent = ""; said.textContent = "The desk doesn't answer. Trying again…";
        await new Promise(r => setTimeout(r, 5000));
        continue;
      }
      code.textContent = ask.code;
      said.textContent = "Open the companion on the owner's phone: it shows this code. Allow this screen there.";
      const until = Date.now() + 290000; // a code holds 5 minutes; then a new one
      let state = "waiting";
      while (state === "waiting" && Date.now() < until) {
        try { ({ state } = await fetch("/api/screen/wait?id=" + encodeURIComponent(ask.id)).then(r => r.json())); }
        catch { await new Promise(r => setTimeout(r, 3000)); }
      }
      if (state === "allowed") return location.reload(); // the pass is set: the desk itself loads
      if (state === "refused") { code.textContent = ""; said.textContent = "The owner's phone refused this screen."; return; }
    }
  })();
}

// the claim by QR code (Gab, 2026-11-23): this screen is near the board (its own, or a computer on its cable) and
// the desk has no owner, so it shows a code; the phone that scans it opens the companion, installs it and claims the
// desk over the WiFi with it. The code holds a few minutes and opens once: the card asks for the current one again.
// It stays until the desk has an owner (then watch() reloads into the lock screen); × hides it until the next load
async function claimCard() {
  const card = document.createElement("div");
  card.style.cssText = "position:fixed;top:16px;right:16px;z-index:9999;width:min(300px,calc(100vw - 32px));background:var(--panel);color:var(--fg);border:1px solid var(--panel-border);border-radius:12px;box-shadow:var(--shadow);padding:16px;display:flex;flex-direction:column;gap:10px;font-size:14px;line-height:1.45;-webkit-user-select:text;user-select:text";
  const head = document.createElement("div");
  head.style.cssText = "display:flex;justify-content:space-between;align-items:center;gap:8px";
  const title = Object.assign(document.createElement("b"), { textContent: "This desk has no owner yet" });
  const shut = Object.assign(document.createElement("button"), { textContent: "×", title: "Hide", ariaLabel: "Hide" });
  shut.style.cssText = "background:none;border:0;color:var(--muted);font-size:20px;cursor:pointer;padding:0 4px";
  shut.onclick = () => { card.remove(); clearTimeout(timer); };
  head.append(title, shut);
  // a QR code reads dark on light, whatever the desk's colours
  const qr = document.createElement("div");
  qr.style.cssText = "background:#fff;border-radius:8px;padding:8px;line-height:0";
  const code = document.createElement("div");
  code.style.cssText = "font-size:26px;letter-spacing:.18em;text-align:center;color:var(--accent);font-variant-numeric:tabular-nums";
  const said = document.createElement("div");
  said.style.color = "var(--muted)";
  card.append(head, qr, code, said);
  document.body.append(card);
  let timer;
  const show = async () => {
    const got = await fetch("/api/trust/code").then(r => r.ok ? r.json() : null).catch(() => null);
    if (!got) { card.remove(); return; } // an owner meanwhile, or out of reach
    qr.innerHTML = got.qr || "";
    qr.hidden = !got.qr;
    qr.querySelector("svg")?.setAttribute("style", "width:100%;height:auto;display:block");
    code.textContent = got.code.slice(0, 4) + "-" + got.code.slice(4);
    said.textContent = !got.desk ? "The desk is on no WiFi yet: give it one first, so the phone can reach it."
      : got.qr ? "Scan it with your phone, on the same WiFi: it opens the companion, to install it and claim this desk."
      : "Open the companion on your phone, on the same WiFi, and type this code to claim the desk at " + got.desk + ".";
    timer = setTimeout(show, Math.max(5, got.left - 20) * 1000); // the next code just before this one ends
  };
  show();
}
