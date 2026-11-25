// The commands of this session, shared by TermNL's two windows: what TermNL hands to the page (run), the log the
// Terminal shows (history, bus), one command's line (commandLine).
import { start, apps, running, close } from "../../../shared/desk.js";
import { changed } from "../../../shared/api.js";
import { el } from "../../../utils/dom.js";

export const bus = new EventTarget();
export const history = []; // every command of this session, for the Terminal

export async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "X-Desk": "1", "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "the device answered " + r.status);
  return d;
}

export function noted(entry) {
  history.push(entry);
  bus.dispatchEvent(new CustomEvent("command", { detail: entry }));
  if (entry.how === "ran" && /^(mkdir|touch|mv) /.test(entry.command)) changed(); // every open folder looks again
}

// a command TermNL hands to the page: opening a folder, the music, the sound's level, the light are the desk's own, as on
// the old desk (its services/device.js and media.js, carried over: Gab, 23 Nov, "I ask Terminal to play some music,
// and I remember that it was working on the Orange Pi ... nothing is happening"); timers are not wired yet, and say so
const homePath = w => w.replace(/^"?\$HOME/, "").replace(/['"]/g, "").replace(/\\(.)/g, "$1").replace(/^\/+/, "");
export async function run(command) {
  const text = command.replace(/\s*&\s*$/, ""), program = text.split(" ")[0];
  let res;
  if (text.startsWith("#") || /^(GET|POST|PUT|PATCH|DELETE) /.test(text)) res = { how: "" };
  else if (program === "xdg-open" || program === "x-terminal-emulator") {
    const path = homePath(text.slice(program.length).trim());
    if (program === "xdg-open") document.dispatchEvent(new CustomEvent("desk:open", { detail: { item: { path, name: path.split("/").pop() || "Home", kind: "folder" } } }));
    else start("terminal");
    res = { how: "on the desk" };
  } else if (program === "mousepad") {  // a file to write: the Reader, in Edit
    const path = homePath(text.slice(program.length).trim()), item = { path, name: path.split("/").pop(), kind: "note" };
    start("reader", item)?.app?.show(item, null, true);
    res = { how: "on the desk" };
  } else if (program === "mpc") res = { how: "on the desk", reply: await music(homePath(text.slice(4))) };
  else if (program === "setsid" || text.startsWith("pkill -x ")) res = onDesk(text);
  else if (light(text) || loud(text)) res = { how: "on the desk" };
  else if (/^(brightnessctl|pactl|systemd-run) /.test(text)) res = { how: "not yet", why: "not wired in the new desk yet" };
  else {
    try {
      const r = await api("/api/exec", { command: text });
      res = r.ran ? { how: r.code === 0 ? "ran" : "failed", out: (r.out + r.err).trim() } : { how: r.group ? "simulated" : "refused", why: r.why };
    } catch (e) { res = { how: "failed", why: e.message }; }
  }
  const entry = { command: text, out: "", ...res };
  noted(entry);
  return entry;
}

// ---- the desk's own apps: what the desk tells TermNL with each sentence (its apps, by their names and what else people
// call them, and the ones open), and the open-app and close-app skills' commands ("setsid 'slides'", "pkill -x 'slides'")
// done on its windows (Gab, 24 Nov: "open slide, open music, open file system works and actually control the desk") ----
const named = a => ({ value: a.id, names: [a.name, ...(a.said || [])] });
export function own() {
  const all = apps().filter(a => a.launcher), open = running();
  return { apps: all.map(named), running: all.filter(a => open.includes(a.id)).map(named) };
}
function onDesk(text) {
  const id = text.split(" ").pop().replace(/['"]/g, ""), app = apps().find(a => a.id === id);
  if (!app) return { how: "not on the desk", reply: "There is no app called \u201c" + id + "\u201d on the desk." };
  if (text.startsWith("setsid ")) { start(id); return { how: "on the desk" }; }
  if (!running().includes(id)) return { how: "on the desk", reply: app.name + " isn't open." };
  close(id);
  return { how: "on the desk" };
}

// ---- the music skills ("mpc play", "mpc searchplay any 'nightcall'", "mpc next"…): the desk's Player plays them, on
// the screen showing the desk, and says what it really did (the old desk's media.js, player.run) ----
const label = t => t.name + (t.artist ? ", by " + t.artist : "");
const shuffled = list => { const a = [...list]; for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const tracks = async name => (await api("/api/music?q=" + encodeURIComponent(name || ""))).tracks
  .map(t => ({ ...t, kind: "track" }));
const playerOpen = () => document.querySelector("app-player");
function playList(list) {  // the Player opened (or brought forward) on these tracks, the first one playing
  const cover = list[0].cover ? [{ kind: "picture", path: list[0].cover }] : [];
  start("player", list[0], [...list, ...cover]);
}
async function music(command) {
  const [verb, ...rest] = command.split(" ");
  const p = playerOpen(), t = p?.queue?.[p.at];
  if (verb === "searchplay") {
    const name = rest.slice(1).join(" "); // after "any"
    const found = await tracks(name);
    if (!found.length) return "I found nothing called \u201c" + name + "\u201d in Music.";
    playList(found);
    return "Playing " + label(found[0]) + (found.length > 1 ? ", and " + (found.length - 1) + " more." : ".");
  }
  if (verb === "play") {
    // "play some music", "shuffle my music", "play something": the whole library in a new random order, whatever the
    // Player holds (Gab, 23 Nov: it carried on with the album open, "which is a bit boring"); only a track paused
    // halfway carries on, as TermNL has no "resume" of its own
    if (t && p.audio.paused && p.audio.currentTime > 0 && !p.audio.ended) { p.audio.play().catch(() => {}); return "Carrying on with " + label(t) + "."; }
    const all = shuffled(await tracks(""));
    if (!all.length) return "There is no music in the Music folder yet.";
    playList(all);
    return "Playing " + label(all[0]) + ", then " + (all.length - 1) + " more in any order.";
  }
  if (verb === "current") return t ? (p.audio.paused ? "Paused on " : "This is ") + label(t) + (t.album ? ", from " + t.album : "") + "." : "Nothing is playing.";
  if (!t) return "Nothing is playing.";
  if (verb === "pause") { p.audio.pause(); return "Paused."; }
  if (verb === "stop") { p.audio.pause(); p.audio.currentTime = 0; return "Stopped."; }
  if (verb === "next") { if (p.at >= p.queue.length - 1) return "That was the last track."; p.play(p.at + 1); return "Next: " + label(p.queue[p.at]) + "."; }
  if (verb === "prev") { if (p.audio.currentTime > 3) p.audio.currentTime = 0; else p.play(p.at - 1); return "Back to " + label(p.queue[p.at]) + "."; }
  return "The player doesn't know \u201c" + verb + "\u201d.";
}

// the sound's level is the Player's own, the page's (the old desk's: "pactl set-sink-volume @DEFAULT_SINK@ 30%", "+10%",
// "-10%"; "set-sink-mute … 1" or 0); the light is the veil over the desk, as the quick panel's slider (its key)
let level = 0.5; // where the volume skill starts counting
function loud(text) {
  const v = /^pactl set-sink-volume @DEFAULT_SINK@ ([+-]?)(\d+)%$/.exec(text), m = /^pactl set-sink-mute @DEFAULT_SINK@ ([01])$/.exec(text);
  const a = playerOpen()?.audio;
  if (v) {
    level = Math.max(0, Math.min(100, v[1] ? (a ? a.volume : level) * 100 + (v[1] === "-" ? -v[2] : +v[2]) : +v[2])) / 100;
    if (a) a.volume = level;
  }
  if (m && a) a.muted = m[1] === "1";
  return !!(v || m);
}
function light(text) {
  const m = /^brightnessctl set (\d+)%([+-]?)$/.exec(text), dim = document.getElementById("dim");
  if (!m || !dim) return false;
  let now = 100;
  try { now = +localStorage.getItem("next.brightness") || 100; } catch { /* not kept */ }
  const v = Math.max(35, Math.min(100, m[2] === "+" ? now + +m[1] : m[2] === "-" ? now - +m[1] : +m[1])); // never fully dark, as the slider
  dim.style.opacity = (1 - v / 100) * 0.55;
  try { localStorage.setItem("next.brightness", v); } catch { /* not kept */ }
  return true;
}

// a command line: the command, then what became of it
export function commandLine(r) {
  const c = el("div", "tn-cmd");
  c.append(el("code", "", r.command));
  if (r.how) c.append(el("span", "tn-how" + (/failed|refused/.test(r.how) ? " bad" : ""), r.how));
  if (r.why) c.title = r.why;
  return c;
}
