// Mesh: the radio's conversations on the desk (mesh/ on the board, the desk's own since 24 Nov). One tab per channel and per
// direct conversation; today's messages from the board's archive, then the new ones as they come
// (/api/mesh/wait). What you send shows what became of it: sending, heard (by the mesh), delivered (to
// the one it was for), failed. Nodes lists who the radio knows; a tap on one starts a direct message.
import { I } from "../../../shared/icons.js";
import { row, toggle, section } from "../../../shared/controls.js";
import { appPref, setAppPref } from "../../../shared/prefs.js";
import { notify } from "../../../shared/notification.js";  // the card at the top right
import { start } from "../../../shared/desk.js";

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text ?? "" });
const BROADCAST = "!ffffffff", MOST = 200;
const ago = s => { const d = Date.now() / 1000 - s; return d < 90 ? "now" : d < 5400 ? Math.round(d / 60) + " min" : d < 129600 ? Math.round(d / 3600) + " h" : Math.round(d / 86400) + " d"; };
const clock = s => new Date(s * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });

async function call(path, body) {
  const r = await fetch("/api/mesh/" + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "the desk answered " + r.status);
  return d;
}

// ---- a new message heard while no Mesh window is in front of the person: a short beep, made here (no sound file);
// Settings, Mesh: "Sound for a new message" (Gab, 24 Nov: "playing a sound notification, just a small beep sound to say a
// new message have arrived"; "settings from an app or for an app should come from the app itself") ----
const sounding = () => appPref("mesh", "sound", true);
// and a card at the top right, in the drop panel's styling: who, where, the words (Gab, 24 Nov: "I will have loved that
// you respect this styling"); each on or off apart ("we can activate the toast independently from the beep")
const showing = () => appPref("mesh", "line", true);
let audio = null;
// a browser lets a page make sound only after a touch or a key on it: the first one readies the sound
for (const kind of ["pointerdown", "keydown"]) addEventListener(kind, () => { try { audio ||= new AudioContext(); audio.resume(); } catch { /* no sound here */ } }, { once: true, capture: true });
function beep() {
  try {
    audio ||= new AudioContext();
    const t = audio.currentTime, tone = audio.createOscillator(), level = audio.createGain();
    tone.frequency.setValueAtTime(880, t);
    tone.frequency.setValueAtTime(1320, t + 0.09);  // two notes, rising
    level.gain.setValueAtTime(0.0001, t);
    level.gain.exponentialRampToValueAtTime(0.12, t + 0.01);
    level.gain.exponentialRampToValueAtTime(0.0001, t + 0.22);
    tone.connect(level).connect(audio.destination);
    tone.start(t);
    tone.stop(t + 0.25);
  } catch { /* no sound on this screen */ }
}
// a Mesh window in front: the focused window, shown (a minimised window, or one on another desktop, keeps its focus mark
// but is hidden), on a screen being looked at
function inFront() {
  const win = document.querySelector(".win.focused app-mesh")?.closest(".win");
  return document.visibilityState === "visible" && !!win && win.style.display !== "none";
}
function heard(message) {
  if (message.mine || inFront()) return;
  if (sounding()) beep();
  if (!showing()) return;
  const direct = message.to !== BROADCAST, where = direct ? "dm:" + message.from : String(message.channel);
  notify({ icon: I.mesh, app: "Mesh", who: (message.from_name || message.from) + " · " + (direct ? "to you" : message.channel_name || "channel " + message.channel),
    when: clock(message.time), text: message.text || "",
    open: () => { const win = start("mesh"); win?.app?.go?.(where); } });  // the Mesh window, on that conversation
}
// while no Mesh window is open, the board's news is listened to here; an open window listens itself (one request, not two)
let ears = null;
async function listen() {
  if (ears || document.querySelector("app-mesh")) return;
  const signal = (ears = new AbortController()).signal;
  let after = null;
  while (!signal.aborted) {
    try {
      if (after == null) after = (await call("state")).seq;
      const r = await fetch("/api/mesh/wait?after=" + after, { signal });
      const d = await r.json();
      if (!r.ok) throw new Error(d.error);
      after = d.seq;
      for (const e of d.events) if (e.type === "message") heard(e.message);
    } catch {
      if (signal.aborted) return;
      await new Promise(r => setTimeout(r, 4000));  // the board out of reach a moment, or the desk restarting
    }
  }
}
const quiet = () => { ears?.abort(); ears = null; };
listen();

// Dressed in the desk's design system (its tokens and components: .btn, .chip, .field; the fold, 23 Nov): only
// this window's own layout is here.
const STYLE = `
app-mesh .mesh-head { flex: 0 0 auto; display: flex; gap: var(--sp-2); align-items: center; padding: var(--sp-2) var(--sp-3); border-bottom: var(--line) solid var(--border); font-size: var(--fs-xs); }
app-mesh .dot { width: 8px; height: 8px; border-radius: var(--r-round); background: var(--muted); flex: none; }
app-mesh .dot.on { background: var(--accent); }
app-mesh .what { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
app-mesh .day { width: auto; height: calc(var(--control) - var(--sp-2)); padding: 0 var(--sp-2); font-size: var(--fs-xs); }
app-mesh .btn.on, app-mesh .chip.on { background: var(--fg); border-color: var(--fg); color: var(--bg); }
app-mesh .mesh-tabs { flex: 0 0 auto; display: flex; gap: var(--sp-1); padding: var(--sp-2) var(--sp-3) 0; overflow-x: auto; scrollbar-width: none; }
app-mesh .mesh-tabs .chip { flex: 0 0 auto; background: none; color: var(--fg); white-space: nowrap; }
app-mesh .mesh-tabs .chip:hover { border-color: var(--fg); }
app-mesh .mesh-tabs .n { color: var(--accent); }
app-mesh .chip.on .n { color: inherit; }
app-mesh .mesh-talk { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: var(--sp-2); padding: var(--sp-3); }
app-mesh .msg { max-width: 85%; padding: var(--sp-2) var(--sp-3); border-radius: var(--r-2); }
app-mesh .msg.mine { align-self: flex-end; background: var(--fg); color: var(--bg); }
app-mesh .msg.theirs { align-self: flex-start; background: var(--hair); border: var(--line) solid var(--border); }
app-mesh .msg .who { display: flex; gap: var(--sp-2); font-size: var(--fs-xs); opacity: .7; }
app-mesh .msg .words { font-family: var(--font-read); font-size: var(--fs-md); white-space: pre-wrap; overflow-wrap: anywhere; }
app-mesh .msg .state { font-size: var(--fs-xs); opacity: .7; text-align: right; }
app-mesh .msg .state.failed { opacity: 1; color: var(--danger); }
app-mesh .quiet { align-self: center; padding: var(--sp-4) 0; color: var(--muted); font-size: var(--fs-xs); text-align: center; }
app-mesh .mesh-entry { flex: 0 0 auto; display: flex; gap: var(--sp-2); padding: var(--sp-2) var(--sp-3) var(--sp-3); border-top: var(--line) solid var(--border); }
app-mesh .mesh-entry small { align-self: center; min-width: 3ch; color: var(--muted); font-size: var(--fs-xs); font-variant-numeric: tabular-nums; text-align: right; }
app-mesh .mesh-entry small.over { color: var(--danger); }
app-mesh .nodes { display: grid; grid-template-columns: auto 1fr auto auto; gap: 0 var(--sp-3); align-items: baseline; }
app-mesh .nodes button { all: unset; cursor: pointer; display: contents; }
app-mesh .nodes button > span { padding: var(--sp-1) 0; border-bottom: var(--line) solid var(--hair); }
app-mesh .nodes button:hover > span { color: var(--accent); }
app-mesh .nodes .short { font-weight: var(--weight-strong); }
app-mesh .nodes .meta { color: var(--muted); font-size: var(--fs-xs); font-variant-numeric: tabular-nums; }
`;

class AppMesh extends HTMLElement {
  connectedCallback() {
    if (!document.getElementById("app-mesh-style")) document.head.append(Object.assign(el("style"), { id: "app-mesh-style", textContent: STYLE }));
    this.innerHTML = `<div class="mesh-head"><span class="dot"></span><span class="what">Looking for the radio…</span>
        <select class="field day" aria-label="Day" hidden></select><button class="btn nodes-btn" type="button">Nodes</button></div>
      <div class="mesh-tabs" role="tablist"></div>
      <div class="mesh-talk" aria-live="polite"></div>
      <form class="mesh-entry"><input class="field" name="t" placeholder="Message" autocomplete="off" aria-label="Message"><small></small><button class="btn solid">Send</button></form>`;
    this.$ = s => this.querySelector(s);
    this.state = { connected: false, channels: [], nodes: [], me: null };
    this.messages = [];          // the day shown
    this.view = null;            // a channel index, "dm:!id", or "nodes"; first the last channel (a private one: Pantheon)
    this.unread = {};
    this.today = null;
    // the desk's window moves its app once while it builds itself: each start has its own listener, ended when the element leaves
    const alive = this.alive = new AbortController();
    this.$(".nodes-btn").addEventListener("click", () => this.go(this.view === "nodes" ? this.last || "0" : "nodes"));
    this.$(".day").addEventListener("change", e => this.load(e.target.value));
    const input = this.$("input"), count = this.$(".mesh-entry small");
    input.addEventListener("input", () => {
      const n = new TextEncoder().encode(input.value).length;
      count.textContent = n > MOST - 40 ? MOST - n : "";
      count.classList.toggle("over", n > MOST);
    });
    this.$("form").addEventListener("submit", e => { e.preventDefault(); this.send(); });
    quiet();  // this window listens now
    this.start(alive.signal);
  }
  disconnectedCallback() { this.alive.abort(); setTimeout(listen, 0); }  // closed (or moved): listened to here again, unless back

  async start(signal) {
    try {
      const state = await call("state");
      if (signal.aborted) return;
      this.take(state);
      await this.load();
    } catch (e) { return signal.aborted || this.say(e.message); }
    if (!signal.aborted) this.follow(signal);
  }
  // today's messages, or an earlier day's (then nothing new is added, and nothing is sent from there)
  async load(day) {
    const d = await call("messages" + (day ? "?day=" + day : ""));
    if (!day || !this.today) this.today = d.day;  // today is the board's day, as the board answers it
    this.day = d.day;
    this.messages = d.messages;
    this.days(d.days);
    if (this.view !== "nodes" && !this.has(this.view)) this.view = String(this.state.channels.at(-1)?.index ?? 0);
    this.render();
  }
  // the picker, shown as soon as one day other than today is kept: today's file only exists from its first message
  // (24 Nov: the board started at 09:57, its first message came at 09:58, and a window opened between saw no picker)
  days(days) {
    const pick = this.$(".day");
    pick.replaceChildren(...[...new Set([this.today, ...days])].map(x => Object.assign(el("option", "", x === this.today ? "Today" : x), { value: x, selected: x === this.day })));
    pick.hidden = !days.some(x => x !== this.today);
  }
  // after a message, the board's days asked again: today's first file, or midnight passed in a window left open
  async recheck() {
    try {
      const d = await call("messages");
      if (d.day !== this.today) {
        const wasToday = this.day === this.today;
        this.today = d.day;
        if (wasToday) { this.day = d.day; this.messages = d.messages; this.render(); }  // the new day, its message in it
      }
      this.days(d.days);
    } catch {}
  }
  async follow(signal) {
    let after = this.state.seq;
    while (!signal.aborted) {
      let d;
      try {
        const r = await fetch("/api/mesh/wait?after=" + after, { signal });
        d = await r.json();
        if (!r.ok) throw new Error(d.error);
      } catch (e) {
        if (signal.aborted) return;
        this.bar(false, "The desk can't be reached: " + e.message);
        await new Promise(r => setTimeout(r, 4000));
        continue;
      }
      if (d.reset) { try { this.take(await call("state")); await this.load(this.day); } catch {} }
      after = d.seq;
      for (const e of d.events) this.event(e);
    }
  }
  event(e) {
    if (e.type === "link") {
      if (e.state) this.take(e.state);
      else { this.state.connected = false; this.state.problem = e.problem; this.bar(); }
      this.render();
    } else if (e.type === "node") {
      const i = this.state.nodes.findIndex(n => n.id === e.node.id);
      if (i < 0) this.state.nodes.push(e.node); else this.state.nodes[i] = e.node;
      if (this.view === "nodes") this.render();
    } else if (e.type === "message") {
      if (this.day === this.today) {
        this.messages.push(e.message);
        const key = this.key(e.message);
        if (key !== this.view && !e.message.mine) this.unread[key] = (this.unread[key] || 0) + 1;
        this.render();
      }
      heard(e.message);
      this.recheck();
    } else if (e.type === "status") {
      const m = this.messages.find(m => m.id === e.id);
      if (m) { m.status = e.status; this.render(); }
    }
  }
  take(state) {
    this.state = state;
    this.bar();
  }
  bar(on = this.state.connected, words) {
    const s = this.state, me = s.nodes?.find(n => n.me);
    this.$(".dot").classList.toggle("on", on);
    this.$(".what").textContent = words || (on ? (me?.long || s.me) + " · " + s.device + " · " + s.nodes.length + " nodes" : "No radio" + (s.problem ? ": " + s.problem : ""));
  }
  say(words) { this.$(".mesh-talk").replaceChildren(el("div", "quiet", words)); }

  // which conversation a message belongs to: its channel, or the other end of a direct one
  key(m) {
    if (m.to === BROADCAST) return String(m.channel);
    return "dm:" + (m.mine ? m.to : m.from);
  }
  has(view) { return this.state.channels.some(c => String(c.index) === view) || this.messages.some(m => this.key(m) === view); }
  name(id) { const n = this.state.nodes.find(n => n.id === id); return n?.long || n?.short || id; }
  // a tab: a channel, a direct conversation, or the nodes (not show(): the desk's own word, "open this file", given
  // to every app it opens)
  go(view) {
    if (view !== "nodes") { this.last = view; delete this.unread[view]; }
    this.view = view;
    this.render();
    if (view !== "nodes") this.$("input").focus({ preventScroll: true });
  }

  render() {
    const tabs = this.state.channels.map(c => [String(c.index), c.name]);
    for (const m of this.messages) { const k = this.key(m); if (k.startsWith("dm:") && !tabs.some(t => t[0] === k)) tabs.push([k, "@ " + this.name(k.slice(3))]); }
    if (this.view.startsWith("dm:") && !tabs.some(t => t[0] === this.view)) tabs.push([this.view, "@ " + this.name(this.view.slice(3))]);
    this.$(".mesh-tabs").replaceChildren(...tabs.map(([k, label]) => {
      const b = el("button", "chip" + (k === this.view ? " on" : ""), label);
      b.type = "button";
      if (this.unread[k]) b.append(el("span", "n", this.unread[k]));
      b.addEventListener("click", () => this.go(k));
      return b;
    }));
    this.$(".nodes-btn").classList.toggle("on", this.view === "nodes");
    const form = this.$("form");
    form.hidden = this.view === "nodes" || this.day !== this.today;
    form.querySelector("button").disabled = !this.state.connected || !!this.sending;
    if (this.view === "nodes") return this.nodes();
    const pane = this.$(".mesh-talk"), shown = this.messages.filter(m => this.key(m) === this.view);
    if (!shown.length) return this.say(this.day === this.today ? "Nothing here today yet." : "Nothing here that day.");
    pane.replaceChildren(...shown.map(m => {
      const box = el("div", "msg " + (m.mine ? "mine" : "theirs")), who = el("div", "who");
      who.append(el("span", "", m.mine ? "you" : m.from_name || this.name(m.from)), el("span", "", clock(m.time)));
      if (!m.mine && m.hops != null) who.append(el("span", "", m.hops ? m.hops + " hop" + (m.hops > 1 ? "s" : "") : "direct"));
      box.append(who, el("div", "words", m.text));
      if (m.mine && m.status) box.append(el("div", "state" + (m.status.startsWith("failed") ? " failed" : ""), m.status));
      return box;
    }));
    pane.scrollTop = pane.scrollHeight;
  }
  nodes() {
    const list = el("div", "nodes"), nodes = [...this.state.nodes].sort((a, b) => (b.me - a.me) || (b.last_heard || 0) - (a.last_heard || 0));
    for (const n of nodes) {
      const b = el("button");
      b.type = "button";
      const meta = [n.last_heard ? ago(n.last_heard) : "never", n.hops != null ? n.hops + " hops" : null, n.battery != null ? (n.battery > 100 ? "powered" : n.battery + "%") : null].filter(Boolean).join(" · ");
      b.append(el("span", "short", n.short || "?"), el("span", "", (n.long || n.id) + (n.me ? " (this radio)" : "")), el("span", "meta", meta), el("span", "meta", n.snr != null ? n.snr + " dB" : ""));
      if (!n.me) b.addEventListener("click", () => this.go("dm:" + n.id));
      list.append(b);
    }
    this.$(".mesh-talk").replaceChildren(nodes.length ? list : el("div", "quiet", "The radio knows no nodes yet."));
  }

  // one message per press: the box empties at once and Send waits for the radio, so a repeated Enter sends nothing more
  async send() {
    const input = this.$("input"), text = input.value.trim();
    if (!text || this.sending) return;
    const dm = this.view.startsWith("dm:"), button = this.$("form button");
    this.sending = button.disabled = true;
    input.value = "";
    input.dispatchEvent(new Event("input"));
    try {
      await call("send", { text, channel: dm ? 0 : Number(this.view), to: dm ? this.view.slice(3) : null });
    } catch (e) {
      if (!input.value) input.value = text;  // given back, to try again
      const pane = this.$(".mesh-talk");
      pane.append(el("div", "quiet", "Not sent: " + e.message));
      pane.scrollTop = pane.scrollHeight;
    } finally {
      this.sending = false;
      button.disabled = !this.state.connected;
    }
  }
}

// Settings, This radio: what the radio plugged in says of itself (its name, region, preset, role, firmware, and each
// channel open, public or private); set today with the Meshtastic app. Read only, for now (Gab, 24 Nov: "Can we
// imagine managing that into the preference of the mesh app?": stage 1, showing it).
const PRIVACY = { open: "Open: no key", public: "Public: Meshtastic's known key", private: "Private: its own key" };
function thisRadio() {
  // a new message, when the Mesh window isn't in front of the person
  const message = section("A new message", [el("small", "set-note", "When the Mesh window isn't in front of you"),
    row("Sound", "A short beep", toggle("Sound for a new message", sounding(), on => setAppPref("mesh", "sound", on))),
    row("A card", "Who wrote, where, and the words, at the top right",
      toggle("A card for a new message", showing(), on => setAppPref("mesh", "line", on)))]);
  // the radio plugged in, as it says of itself (asked when the page is drawn)
  const radio = section("This radio", [el("small", "set-note", "Asking the radio…")]);
  const fill = (...rows) => radio.replaceChildren(el("h3", "eyebrow", "This radio"), ...rows);
  call("state").then(s => {
    if (!s.connected) return fill(el("small", "set-note", "No radio connected" + (s.problem ? ": " + s.problem : "") + "."));
    const me = s.nodes.find(n => n.me) || {}, r = s.radio || {};
    const value = t => el("span", "mesh-val", t || "—");
    fill(el("small", "set-note", "What the radio plugged in says of itself. Change it, for now, with the Meshtastic app."),
      ...[row("Name", me.short ? "Short name: " + me.short : "", value(me.long || s.me)),
        row("Node", "", value(s.me)),
        row("Region", "Where it may transmit", value(r.region === "unset" ? "Not set: it won't transmit" : r.region)),
        row("Preset", "Its speed against its reach", value(r.preset)),
        row("Role", "", value(r.role)),
        r.hops ? row("Hops", "How far a message is passed on", value(String(r.hops))) : null,
        row("Firmware", "", value(r.firmware)),
        ...s.channels.map(c => row(c.name, c.index === 0 ? "Its primary channel" : "Channel " + c.index, value(PRIVACY[c.privacy] || c.privacy)))].filter(Boolean));
  }).catch(e => fill(el("small", "set-note", "The radio: " + e.message)));
  return [message, radio];
}

export default {
  id: "mesh",
  name: "Mesh",
  said: ["meshtastic", "lora"],
  icon: I.mesh,
  size: [420, 560],
  launcher: true,
  element: AppMesh,
  settings: thisRadio,
};
