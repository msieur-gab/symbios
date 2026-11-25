// The system monitor, with the symbios gauges (.mon-grid, .gauge, .spark): load, memory,
// temperature and disk, read every few seconds while the window is open. Bars move by
// transform, not width: on the board there is no GPU compositing (learned on symbios).
// Below the gauges, Activity: one line per task on the board, a plain bar and the time left;
// queued tasks say "pending", a finished one says "done" for a moment and goes (decided with
// Gab, 2026-10-19). The tasks are the board's own (services/changes.js, signals.py).
import { bus, status, info, wifi } from "../services/device.js";
import { tasks, skew } from "../services/changes.js";

const gb = n => (n / 1073741824).toFixed(1);
const left = s => s >= 90 ? Math.round(s / 60) + " min" : Math.max(1, Math.round(s)) + " s";

class AppSystem extends HTMLElement {
  async connectedCallback() {
    this.innerHTML = `<div><div class="mon-grid">
      <div class="gauge"><h4>CPU load</h4><div class="big" data-v="cpu">—</div><div class="bar"><i data-b="cpu"></i></div><div class="spark"></div></div>
      <div class="gauge"><h4>Memory</h4><div class="big" data-v="mem">—</div><div class="bar"><i data-b="mem"></i></div><small data-v="mem-sub">—</small></div>
      <div class="gauge"><h4>SoC temp</h4><div class="big" data-v="temp">—</div><div class="bar"><i data-b="temp"></i></div><small data-v="up">—</small></div>
      <div class="gauge"><h4>Disk</h4><div class="big" data-v="disk">—</div><div class="bar"><i data-b="disk"></i></div><small data-v="disk-sub">—</small></div>
    </div><div class="activity"><h4>Activity</h4><div class="tasks"></div></div><div class="groups"></div><div class="wifi"></div></div>`;
    this.networks();
    this.spark = this.querySelector(".spark");
    for (let i = 0; i < 22; i++) this.spark.append(document.createElement("i"));
    info().then(a => {
      const off = a.groups.filter(g => !a.allowed.includes(g));
      this.querySelector(".groups").textContent = "really runs: " + (a.allowed.join(", ") || "nothing") + (off.length ? " · simulated: " + off.join(", ") : "") + " · home: " + a.home;
    }).catch(() => {});
    this.tasks = this.querySelector(".tasks");
    this.rows = new Map();
    this.onTasks = () => this.activity();
    bus.addEventListener("tasks", this.onTasks);
    this.activity();
    this.tick();
    this.timer = setInterval(() => this.tick(), 4000);
  }
  disconnectedCallback() { clearInterval(this.timer); clearTimeout(this.soon); bus.removeEventListener("tasks", this.onTasks); }
  // ---- WiFi: where the board is, the networks it knows, adding one. Near the board only
  // (its screen, its cable): that is how a board with no screen is taken to a new place. ----
  async networks(answer, note) {
    const box = this.querySelector(".wifi"), el = (tag, text, cls) => Object.assign(document.createElement(tag), { textContent: text || "", className: cls || "" });
    let now = answer;
    try { now ||= await wifi.now(); } catch (e) { return box.replaceChildren(el("h4", "WiFi"), el("small", e.message + ".")); }
    const here = el("div");
    if (now.ip) {
      // the address to open once the cable is unplugged: this board's WiFi chip can't answer to a name
      here.append("On “" + now.ssid + "”. " + (now.near ? "Without the cable the desk is at " : "Over WiFi the desk is at "), Object.assign(el("a", "http://" + now.ip), { href: "http://" + now.ip }), ".");
    } else here.textContent = "Not on any WiFi.";
    const known = el("div", "", "known");
    for (const n of now.known) {
      const row = el("span", n.ssid);
      if (n.ours && now.near) {
        const forget = el("button", "forget");
        forget.addEventListener("click", async () => { forget.disabled = true; this.networks(await wifi.forget(n.ssid).catch(e => ({ ...now, error: e.message }))); });
        row.append(forget);
      }
      known.append(row);
    }
    const form = el("form", "", "entry");
    form.innerHTML = `<input name="ssid" list="wifi-near" placeholder="Network name" autocomplete="off" spellcheck="false" aria-label="Network name"><datalist id="wifi-near"></datalist>
      <input name="password" type="password" placeholder="Password (none if open)" autocomplete="off" aria-label="Password"><button>Add</button>`;
    form.ssid.addEventListener("focus", async () => { // what is in range, asked once
      for (const n of await wifi.scan().catch(() => [])) form.querySelector("datalist").append(Object.assign(el("option"), { value: n.ssid }));
    }, { once: true });
    form.addEventListener("submit", async e => {
      e.preventDefault();
      const ssid = form.ssid.value.trim();
      if (!ssid) return;
      form.querySelector("button").disabled = true;
      said.textContent = "Trying “" + ssid + "”: this takes up to half a minute…";
      const r = await wifi.add(ssid, form.password.value).catch(e => ({ ...now, error: e.message }));
      this.networks(r, r.error ? "" : r.joined ? "The board is on “" + ssid + "” now." : "Kept. The board will use “" + ssid + "” when it is in range.");
    });
    const said = el("small", now.error ? now.error + "." : note || "");
    // reached over WiFi: what the board knows is shown, changing it waits for the cable
    if (!now.near) return box.replaceChildren(el("h4", "WiFi"), here, known, el("small", "You are reaching the desk over WiFi. To add or forget a network, plug the board in and open it over the cable."));
    box.replaceChildren(el("h4", "WiFi"), here, known, form, said);
  }
  set(key, text) { this.querySelector(`[data-v="${key}"]`).textContent = text; }
  bar(key, pct) { this.querySelector(`[data-b="${key}"]`).style.transform = "scaleX(" + Math.max(0, Math.min(100, pct)) / 100 + ")"; }
  async tick() {
    let s;
    try { s = await status(); } catch { return; } // keep the last values on a blip
    const load = Math.round((s.load[0] / s.cores) * 100), mem = Math.round((s.memory.used / s.memory.total) * 100), disk = Math.round((s.disk.used / s.disk.total) * 100);
    this.set("cpu", load + "%"); this.bar("cpu", load);
    this.spark.firstChild.remove();
    const i = document.createElement("i");
    i.style.transform = "scaleY(" + Math.max(6, Math.min(100, load)) / 100 + ")";
    this.spark.append(i);
    this.set("mem", mem + "%"); this.bar("mem", mem); this.set("mem-sub", gb(s.memory.used) + " / " + gb(s.memory.total) + " GB");
    this.set("temp", s.temp == null ? "—" : s.temp + "°"); this.bar("temp", s.temp == null ? 0 : ((s.temp - 20) / 60) * 100);
    const h = Math.floor(s.uptime / 3600), m = Math.floor((s.uptime % 3600) / 60);
    this.set("up", s.host + " · up " + (h >= 24 ? Math.floor(h / 24) + "d " : "") + (h % 24) + "h " + m + "m");
    this.set("disk", disk + "%"); this.bar("disk", disk); this.set("disk-sub", gb(s.disk.used) + " / " + gb(s.disk.total) + " GB");
  }
  // ---- Activity: the board's heavy work as signals.py tells it; a line is added or removed only when a
  // task arrives or ends, the rest is a bar's transform and a text change. A task without an expected
  // length shows its bar empty and "running" until it has one; one running past it shows "almost" ----
  activity() {
    clearTimeout(this.soon);
    const now = Date.now() / 1000 - skew, seen = new Set();
    for (const t of tasks) {
      if (t.ended && now - t.ended > 3) continue; // "done" for a moment, then gone
      seen.add(t.id);
      let row = this.rows.get(t.id);
      if (!row) {
        row = document.createElement("div");
        row.innerHTML = `<span class="name"></span><div class="bar"><i></i></div><span class="time"></span>`;
        this.rows.set(t.id, row);
        this.tasks.append(row);
      }
      const run = t.state === "running", gone = run && t.expect ? now - t.since : 0;
      const pct = t.ended ? 100 : run && t.expect ? Math.min(99, (gone / t.expect) * 100) : 0;
      row.className = "task" + (t.state === "pending" ? " pending" : "");
      row.querySelector(".name").textContent = t.name;
      row.querySelector("i").style.transform = "scaleX(" + pct / 100 + ")";
      row.querySelector(".time").textContent = t.state === "done" ? "done" : t.state === "failed" ? "failed" : !run ? "pending"
        : !t.expect ? "running" : t.expect - gone > 1 ? left(t.expect - gone) : "almost";
    }
    for (const [id, row] of this.rows) if (!seen.has(id)) { row.remove(); this.rows.delete(id); }
    this.tasks.dataset.empty = this.rows.size ? "" : "Nothing running.";
    if (this.rows.size) this.soon = setTimeout(() => this.activity(), 1000); // the bars move while there is work
  }
}
customElements.define("app-system", AppSystem);
