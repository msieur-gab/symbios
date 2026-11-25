// The device behind the desk: its files, its numbers, and the commands the skills hand over.
// A command either belongs to the desk itself (open an app, open a file: no shell involved)
// or goes to the server, which runs it only when a skill declares that form.

export const bus = new EventTarget();
const emit = (type, detail) => bus.dispatchEvent(new CustomEvent(type, { detail }));
export const history = []; // every command of this session, for the Terminal window

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : undefined);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "the device answered " + r.status);
  return data;
}
export const list = path => api("/api/fs/list?path=" + encodeURIComponent(path));
export const read = path => api("/api/fs/read?path=" + encodeURIComponent(path));
export const write = (path, text) => api("/api/fs/write", { path, text });
export const music = name => api("/api/music?q=" + encodeURIComponent(name || "")).then(d => d.tracks);
// a web address → its article as markdown in ~/Articles, made by the board: { path, title, words }
export const article = url => api("/api/articles", { url }).then(a => (emit("files"), a));
export const articles = () => api("/api/articles").then(d => d.articles); // the library, newest first
export const ask = q => api("/api/ask?q=" + encodeURIComponent(q)); // the articles and memos about it, or none (ask.py)
export const say = (text, session) => api("/api/say", { text, session }); // a sentence for TermNL → its reply
// the WiFi networks the board knows; only answered near the board (its screen, its cable)
export const wifi = { now: () => api("/api/wifi"), scan: () => api("/api/wifi/scan").then(d => d.networks),
  add: (ssid, password) => api("/api/wifi/add", { ssid, password }), forget: ssid => api("/api/wifi/forget", { ssid }) };
export const status = () => api("/api/status");
export const info = () => api("/api/info");

// what the skills call a desktop program → the desk app that plays its part
const SURFACE = { "x-terminal-emulator": "terminal", "xdg-open": "files", mousepad: "editor" };
// "$HOME'/Pictures/holiday photos'" → "Pictures/holiday photos"
const homePath = word => word.replace(/^"?\$HOME/, "").replace(/['"]/g, "").replace(/\\(.)/g, "$1").replace(/^\/+/, "");

// Brightness is the desk's own, not the host's: a veil over the page (as symbios dims),
// remembered on that screen. The host's real backlight has its own keys. "brightnessctl set 40%", "10%+", "10%-".
const BRIGHT_KEY = "desk.brightness";
export function brightness(set) {
  let v = 100;
  try { v = +(localStorage.getItem(BRIGHT_KEY) ?? 100); } catch { /* not kept */ }
  if (set != null) {
    v = Math.max(0, Math.min(100, set));
    try { localStorage.setItem(BRIGHT_KEY, v); } catch { /* not kept */ }
  }
  const dim = document.getElementById("dim");
  if (dim) dim.style.opacity = (1 - v / 100) * 0.55;
  return v;
}
// Volume is the desk's own too: the level of its player. The host's system volume has its own keys.
// "pactl set-sink-volume @DEFAULT_SINK@ 30%", "+10%", "-10%"; "set-sink-mute … 1" or 0.
// The media service registers itself here (it imports this file, not the other way round).
export const sound = { volume: null, mute: null };
function loud(text) {
  const v = /^pactl set-sink-volume @DEFAULT_SINK@ ([+-]?)(\d+)%$/.exec(text), m = /^pactl set-sink-mute @DEFAULT_SINK@ ([01])$/.exec(text);
  if (v && sound.volume) sound.volume(v[1] === "-" ? -v[2] : +v[2], !!v[1]);
  if (m && sound.mute) sound.mute(m[1] === "1");
  return !!(v || m);
}
// The music commands the skills send ("mpc play", "mpc next", "mpc searchplay any 'nightcall'")
// go to the desk's own player, which answers with what it really did.
export const player = { run: null };
function light(text) {
  const m = /^brightnessctl set (\d+)%([+-]?)$/.exec(text);
  if (!m) return false;
  const now = brightness();
  brightness(m[2] === "+" ? now + +m[1] : m[2] === "-" ? now - +m[1] : +m[1]);
  return true;
}

// a command TermNL ran or simulated on the device: kept with the page's own, for the Terminal window
export function noted(entry) {
  history.push(entry);
  emit("command", entry);
  if (entry.how === "ran" && /^(mkdir|touch|mv) /.test(entry.command)) emit("files");
}

// one command → { command, how, out, why }; how is "ran", "simulated", "on the desk", "refused" or "failed"
export async function run(command) {
  const text = command.replace(/\s*&\s*$/, ""); // "firefox &": the desk has no background jobs
  const program = text.split(" ")[0];
  let res;
  if (text.startsWith("#") || /^(GET|POST|PUT|PATCH|DELETE) /.test(text)) {
    res = { how: "", out: "" }; // a note, or a web request the browser already made
  } else if (program === "mpc" && player.run) {
    res = { how: "on the desk", out: "", reply: await player.run(homePath(text.slice(4))) };
  } else if (light(text) || loud(text) || text.startsWith("systemd-run ")) {
    res = { how: "on the desk", out: "" }; // the screen's light, the speakers' level; timers ring in the page
  } else if (program in SURFACE) {
    const path = homePath(text.slice(program.length).trim());
    emit("open", { app: SURFACE[program], path });
    res = { how: "on the desk", out: "" };
  } else {
    try {
      const r = await api("/api/exec", { command: text });
      if (r.ran) res = { how: r.code === 0 ? "ran" : "failed", out: (r.out + r.err).trim(), row: r.row || undefined };
      else res = { how: r.group ? "simulated" : "refused", out: "", why: r.why };
      if (r.ran && r.group === "files") emit("files");
    } catch (e) {
      res = { how: "failed", out: "", why: e.message };
    }
  }
  const entry = { command: text, ...res };
  history.push(entry);
  emit("command", entry);
  return entry;
}
