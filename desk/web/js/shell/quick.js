// quick.js — the right island and the quick panel behind it, after SymbiOS v1 (core/quicksettings.js), itself
// inspired by Zorin OS (Gab, 23 Nov: "our bottom right island was greatly inspired by the Zorin OS").
// The island says what is live at a glance: a Meshtastic node, a Bluetooth device, a hot board, the WiFi,
// the clock. The panel holds quick actions only ("let us start with the quick panel holds quick actions"):
// at the top the small buttons, Monitor, Settings, full screen, lock; then the tiles, WiFi, Bluetooth,
// the mode, the Meshtastic node, each opening its list inside the panel ("what I think is cool … the
// Wi-Fi is opening this panel"); the brightness; one line on the board. Managing things belongs to Settings.
// On the laptop the WiFi and Bluetooth are only looked at (next/wifi.py, next/devices.py).
import { launch } from "./wm.js";
import { status, uptime } from "../shared/status.js";
import { lock } from "./lock.js";
import { applyTheme, currentTheme } from "../shared/theme.js";
import { I } from "../shared/icons.js";
import { el } from "../utils/dom.js";

const qs = document.getElementById("qs"), trayWifi = document.getElementById("tray-wifi"), trayHot = document.getElementById("tray-hot"), trayBt = document.getElementById("tray-bt"), trayMesh = document.getElementById("tray-mesh"), dim = document.getElementById("dim");
let timer = null, net = null, inRange = null, bt = null, mesh = null, open = "", said = "";  // open: the tile whose list is shown

async function get(url, body) {
  const r = await fetch(url, body ? { method: "POST", headers: { "X-Desk": "1", "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.status);
  return d;
}

// the island: the WiFi glyph, crossed out when the device is on no network
export async function syncWifi() {
  try { net = await get("/api/wifi"); } catch { net = null; }
  trayWifi.innerHTML = net?.ssid ? I.wifi : I.wifiOff;
  trayWifi.title = net?.ssid ? `On “${net.ssid}”` : "Not on any WiFi";
  if (qs.classList.contains("open") && !qs.contains(document.activeElement)) build();
}

// the board in one line at the panel's foot; the island marks a hot board (70° and above) at all times
async function read() {
  try {
    const s = await status();
    hot(s.temp);
    const foot = qs.querySelector(".qs-board");
    if (!foot) return;
    foot.querySelector(".t").textContent = s.temp == null ? "—" : s.temp + "°";
    foot.querySelector(".t").classList.toggle("hot", s.temp >= 70);
    foot.querySelector(".r").textContent = ` · CPU ${Math.round(s.load[0] / s.cores * 100)}% · memory ${Math.round(s.memory.used / s.memory.total * 100)}% · up ${uptime(s.uptime)}`;
  } catch { /* keep the last numbers */ }
}
function hot(t) {
  trayHot.hidden = !(t >= 70);
  trayHot.title = t >= 70 ? `The board is at ${t}°` : "";
}

// the sound's level (PipeWire, devices.py): read when the panel opens; sent a moment after the slider stops, not
// once per pixel. The speaker mutes and unmutes, the level kept (Gab, 23 Nov: "clicking on the volume icon should
// mute the sound, clicking on it should restore the previous sound level setting")
let sound = null, muted = false, soundTimer = null;
function paintSound() {
  const row = qs.querySelector(".sound");
  if (!row) return;
  row.hidden = sound == null;
  row.classList.toggle("muted", muted);
  row.querySelector("input").value = sound ?? 0;
  const b = row.querySelector(".mute-btn");
  b.innerHTML = muted || sound === 0 ? I.mute : I.sound;
  b.title = b.ariaLabel = muted ? "Sound back" : "Mute";
}
async function syncSound() {
  try { const v = await get("/api/volume"); sound = v.level; muted = !!v.muted; } catch { sound = null; }
  paintSound();
}
function setSound(level) {
  sound = level;
  if (level) muted = false;  // moving the slider up is wanting to hear (the server unmutes too)
  paintSound();
  clearTimeout(soundTimer);
  soundTimer = setTimeout(() => get("/api/volume", { level }).catch(() => {}), 120);
}
async function toggleMute() {
  muted = !muted;
  paintSound();
  try { const v = await get("/api/volume", { muted }); sound = v.level; muted = !!v.muted; } catch { /* as shown */ }
  paintSound();
}

// brightness: a veil over the desk, as v1 dims (never fully dark), remembered on this screen
const BRIGHT = "next.brightness";
const bright = () => { try { return +localStorage.getItem(BRIGHT) || 100; } catch { return 100; } };
function setBright(v) {
  dim.style.opacity = (1 - v / 100) * 0.55;
  try { localStorage.setItem(BRIGHT, v); } catch { /* not kept */ }
}


// a line of a list (components.css .row): glyph · name · meta
function row(tag, glyph, name, meta, cls = "") {
  const r = el(tag, "row " + cls);
  r.append(Object.assign(el("span", "g"), { innerHTML: glyph }), el("span", "name", name));
  if (meta != null) r.append(el("span", "meta", meta));
  return r;
}

function wifiPanel() {
  const box = el("div", "card");
  if (!net) { box.append(el("small", "muted", "The WiFi can't be read here.")); return box; }
  box.append(el("div", "", net.ssid ? `On “${net.ssid}”` + (net.ip ? ` · ${net.ip}` : "") : "Not on any WiFi"));
  if (net.known.length) {
    box.append(el("h4", "eyebrow", "Known"));
    const known = el("div", "chips");
    for (const n of net.known) {
      const chip = el("span", "chip" + (n.ssid === net.ssid ? " here" : ""), n.ssid);
      if (n.ours && !net.readonly) {
        const forget = el("button", "btn quiet", "forget");
        forget.onclick = async () => { forget.disabled = true; try { net = await get("/api/wifi/forget", { ssid: n.ssid }); said = net.error || ""; } catch (e) { said = e.message; } build(); syncWifi(); };
        chip.append(forget);
      }
      known.append(chip);
    }
    box.append(known);
  }
  box.append(el("h4", "eyebrow", "In range"));
  if (!inRange) box.append(el("small", "muted", "Looking…"));
  else if (!inRange.length) box.append(el("small", "muted", "Nothing in range."));
  else for (const n of inRange.slice(0, 8)) {
    const b = row("button", I.wifi, n.ssid, "");
    b.querySelector(".g").style.opacity = Math.max(0.3, Math.min(1, (n.signal + 95) / 45));
    if (n.secure) b.querySelector(".meta").innerHTML = I.lockSmall;
    b.onclick = () => { const f = box.querySelector("form"); if (f) { f.ssid.value = n.ssid; f.password.focus(); } };
    box.append(b);
  }
  if (net.readonly) {
    box.append(el("small", "muted", "On the laptop the desk only looks: networks are added on the board."));
  } else {
    const form = el("form");
    form.innerHTML = `<input class="field" name="ssid" placeholder="Network name" autocomplete="off" spellcheck="false" aria-label="Network name">
      <span class="field-wrap"><input class="field" name="password" type="password" placeholder="Password (none if open)" autocomplete="off" aria-label="Password"><button type="button" class="ib eye" aria-label="Show the password" title="Show the password">${I.eye}</button></span>
      <button class="btn go">Add</button>`;
    const eye = form.querySelector(".eye");
    eye.onclick = () => {  // see what was typed before sending it (PLAN.md, 8 Nov: "an eye on the password field")
      const show = form.password.type === "password";
      form.password.type = show ? "text" : "password";
      eye.innerHTML = show ? I.eyeOff : I.eye;
      eye.title = eye.ariaLabel = show ? "Hide the password" : "Show the password";
    };
    form.onsubmit = async e => {
      e.preventDefault();
      const ssid = form.ssid.value.trim();
      if (!ssid) return;
      form.querySelector(".go").disabled = true;
      said = `Trying “${ssid}”: this takes up to half a minute…`;
      box.querySelector(".said").textContent = said;
      try { net = await get("/api/wifi/add", { ssid, password: form.password.value }); said = net.error || (net.joined ? `On “${ssid}” now.` : `Kept: it will be used when “${ssid}” is in range.`); }
      catch (err) { said = err.message; }
      build(); syncWifi();
    };
    box.append(form);
  }
  box.append(el("small", "muted said", said));
  return box;
}

// Bluetooth and the Meshtastic node, read for the island and the tiles
async function syncDevices() {
  [bt, mesh] = await Promise.all([get("/api/bluetooth").catch(() => null), get("/api/mesh").catch(() => null)]);
  const linked = bt?.devices.filter(d => d.connected) || [];
  trayBt.hidden = !linked.length;
  trayBt.title = linked.map(d => d.name).join(", ");
  trayMesh.hidden = !meshOn();
  trayMesh.title = meshOn() ? "Mesh: " + meshName() : "";
  if (qs.classList.contains("open") && !qs.contains(document.activeElement)) build();
}

function btPanel() {
  const box = el("div", "card");
  if (!bt?.adapter) { box.append(el("small", "muted", "No Bluetooth here.")); return box; }
  box.append(el("div", "", bt.on ? "Bluetooth is on" : "Bluetooth is off"), el("h4", "eyebrow", "Devices"));
  if (!bt.devices.length) box.append(el("small", "muted", "None paired yet."));
  for (const d of bt.devices) box.append(row("div", I.bluetooth, d.name, d.connected ? "connected" : "paired", d.connected ? "here" : ""));
  box.append(el("small", "muted", "Pairing and connecting come with Settings, on the board."));
  return box;
}

// a radio Mesh is talking to (named by its node), else one plugged in by USB (named by its USB product)
function meshOn() { return !!(mesh?.radio || mesh?.nodes.length); }
function meshName() { return mesh?.radio?.name || mesh?.nodes[0]?.name || ""; }

function meshPanel() {
  const box = el("div", "card");
  if (!meshOn()) {
    box.append(el("div", "", "No node plugged in"), el("small", "muted", "Plug a Meshtastic radio into a USB port: it shows here."));
    return box;
  }
  if (mesh.radio) box.append(row("div", I.mesh, mesh.radio.name, "Connected" + (mesh.radio.short ? " · " + mesh.radio.short : ""), "here"));
  for (const n of mesh.nodes) {
    if (mesh.radio && !n.boot) continue;  // the same radio, by its USB name
    box.append(row("div", I.mesh, n.name, n.maker, "here"));
    if (n.boot) box.append(el("small", "muted", "It is in its bootloader (firmware update mode), not running Meshtastic: restart it to use it."));
  }
  box.append(el("small", "muted", "Its name, region and channels: Settings, under Mesh."));
  return box;
}

// the mode tile names the mode the desk is in, Dark with a moon or Light with a sun; a tap goes to the other,
// to the theme last worn there (Gab, 23 Nov: "if you click dark, then it should become light, and then change
// the icon ... a sun and a moon")
const LIGHTS = ["light", "blue"];
function flipMode(dark) {
  const keep = (k, v) => { try { localStorage.setItem(k, v); } catch { /* not kept */ } };
  const last = (k, d) => { try { return localStorage.getItem(k) || d; } catch { return d; } };
  keep(dark ? "next.lastDark" : "next.lastLight", currentTheme());
  applyTheme(dark ? last("next.lastLight", "light") : last("next.lastDark", "phosphor"));
}

function tile(id, on, glyph, name, sub, more = true) {
  return `<button class="qtog ${id}${on ? " on" : ""}${open === id ? " open" : ""}" data-tile="${id}"><span class="ic">${glyph}</span><span><b>${name}</b><small>${sub}</small></span>${more ? `<span class="more">${open === id ? "⌃" : "⌄"}</span>` : ""}</button>`;
}

function build() {
  const dark = !LIGHTS.includes(currentTheme());
  const linked = bt?.devices.filter(d => d.connected) || [];
  const full = !!document.fullscreenElement;
  qs.innerHTML = `<div class="qs-head">
      <button class="ib round" data-app="monitor" title="Monitor: temperature, CPU, memory, disk" aria-label="Monitor">${I.monitor}</button>
      <button class="ib round" data-app="settings" title="Settings" aria-label="Settings">${I.settings}</button>
      <button class="ib round full" title="${full ? "Leave full screen" : "Full screen"}" aria-label="Full screen">${full ? I.unfull : I.full}</button>
      <button class="ib round lock" title="Lock the desk" aria-label="Lock">${I.lockSmall}</button></div>
    <div class="qs-sliders">
      <div class="slider-row bright">${I.sun}<input type="range" min="35" max="100" value="${bright()}" aria-label="Brightness"></div>
      <div class="slider-row sound"><button class="ib mute-btn"></button><input type="range" min="0" max="100" aria-label="Sound"></div>
    </div>
    <div class="qs-grid">
      ${tile("wifi", !!net?.ssid, net?.ssid ? I.wifi : I.wifiOff, "Wi-Fi", "")}
      ${tile("bt", !!bt?.on, I.bluetooth, "Bluetooth", !bt?.adapter ? "None here" : !bt.on ? "Off" : linked.length ? "" : "On")}
      ${tile("mode", false, dark ? I.moon : I.sun, dark ? "Dark" : "Light", currentTheme(), false)}
      ${tile("mesh", meshOn(), I.mesh, "Mesh", meshOn() ? "" : "Not connected")}
    </div>
    <div class="qs-list"></div>
    <div class="qs-foot qs-board"><span><span class="t">—</span><span class="r"></span></span></div>`;
  qs.querySelector(".qtog.wifi small").textContent = net?.ssid || "Off";
  if (linked.length) qs.querySelector(".qtog.bt small").textContent = linked[0].name;
  if (meshOn()) qs.querySelector(".qtog.mesh small").textContent = meshName();
  for (const t of qs.querySelectorAll("[data-tile]")) t.onclick = () => {
    const id = t.dataset.tile;
    if (id === "mode") { flipMode(dark); return build(); }
    open = open === id ? "" : id;
    if (open === "wifi") scan();
    if (open === "bt" || open === "mesh") syncDevices();
    build();
  };
  const list = qs.querySelector(".qs-list");
  if (open === "wifi") list.append(wifiPanel());
  if (open === "bt") list.append(btPanel());
  if (open === "mesh") list.append(meshPanel());
  qs.querySelector(".bright input").oninput = e => setBright(+e.target.value);
  qs.querySelector(".sound input").oninput = e => setSound(+e.target.value);
  qs.querySelector(".mute-btn").onclick = toggleMute;
  paintSound();
  qs.querySelectorAll("[data-app]").forEach(b => b.onclick = () => { launch(b.dataset.app); closeQS(); });
  qs.querySelector(".full").onclick = () => { full ? document.exitFullscreen?.() : document.documentElement.requestFullscreen?.().catch(() => {}); };
  qs.querySelector(".lock").onclick = () => { closeQS(); lock(); };
  read();
}
document.addEventListener("fullscreenchange", () => { if (qs.classList.contains("open")) build(); });

async function scan() {
  inRange = null;
  try { inRange = (await get("/api/wifi/scan")).networks; } catch { inRange = []; }
  if (open === "wifi" && qs.classList.contains("open")) {
    const form = qs.querySelector("form"), typed = form && [form.ssid.value, form.password.value];
    build();
    const again = qs.querySelector("form");
    if (typed && again) [again.ssid.value, again.password.value] = typed;  // what was being typed stays
  }
}

export function openQS() { said = ""; build(); syncWifi(); syncDevices(); syncSound(); qs.classList.add("open"); clearInterval(timer); timer = setInterval(read, 3000); }
export function closeQS() { qs.classList.remove("open"); clearInterval(timer); }

document.getElementById("tray-btn").addEventListener("click", () => qs.classList.contains("open") ? closeQS() : openQS());
document.addEventListener("pointerdown", e => { if (qs.classList.contains("open") && !qs.contains(e.target) && !e.target.closest("#tray-btn")) closeQS(); }, true);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeQS(); });
trayHot.innerHTML = I.hot;
trayBt.innerHTML = I.bluetooth;
trayMesh.innerHTML = I.mesh;
setBright(bright());
syncWifi();
setInterval(syncWifi, 30000);
syncDevices();
setInterval(syncDevices, 10000);  // a node plugged in shows within seconds
read();
setInterval(read, 15000);  // the island's hot mark, while the panel is closed too
