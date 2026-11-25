// Monitor: the board's load, memory, temperature and disk, read every few seconds while the window is open, and
// the board's tasks (Activity) under its gauges (desk/app/js/components/app-system.js, with symbios's gauges).
import { status, uptime } from "../../shared/status.js";
import { I } from "../../shared/icons.js";

const gb = n => (n / 1073741824).toFixed(1);

class AppMonitor extends HTMLElement {
  connectedCallback() {
    if (this.spark) return;
    this.innerHTML = `<div class="mon"><div class="mon-grid">
      <div class="card gauge"><h4 class="eyebrow">CPU load</h4><div class="big" data-v="cpu">—</div><div class="bar"><i data-b="cpu"></i></div><div class="spark"></div></div>
      <div class="card gauge"><h4 class="eyebrow">Memory</h4><div class="big" data-v="mem">—</div><div class="bar"><i data-b="mem"></i></div><small data-v="mem-sub">—</small></div>
      <div class="card gauge"><h4 class="eyebrow">Temperature</h4><div class="big" data-v="temp">—</div><div class="bar"><i data-b="temp"></i></div><small data-v="up">—</small></div>
      <div class="card gauge"><h4 class="eyebrow">Disk</h4><div class="big" data-v="disk">—</div><div class="bar"><i data-b="disk"></i></div><small data-v="disk-sub">—</small></div>
    </div><div class="mon-act"><h4 class="eyebrow">Activity</h4><app-activity></app-activity></div><div class="mon-model" data-v="model"></div></div>`;
    this.spark = this.querySelector(".spark");
    for (let i = 0; i < 22; i++) this.spark.append(document.createElement("i"));
    this.tick();
    this.timer = setInterval(() => this.tick(), 3000);
  }
  closing() { clearInterval(this.timer); }
  set(k, t) { this.querySelector(`[data-v="${k}"]`).textContent = t; }
  bar(k, pct) { this.querySelector(`[data-b="${k}"]`).style.transform = `scaleX(${Math.max(0, Math.min(100, pct)) / 100})`; }
  async tick() {
    let s;
    try { s = await status(); } catch { return; }
    const load = Math.round(s.load[0] / s.cores * 100), mem = Math.round(s.memory.used / s.memory.total * 100), disk = Math.round(s.disk.used / s.disk.total * 100);
    this.set("cpu", load + "%"); this.bar("cpu", load);
    this.spark.firstChild.remove();
    const i = document.createElement("i");
    i.style.transform = `scaleY(${Math.max(6, Math.min(100, load)) / 100})`;
    this.spark.append(i);
    this.set("mem", mem + "%"); this.bar("mem", mem); this.set("mem-sub", gb(s.memory.used) + " / " + gb(s.memory.total) + " GB");
    this.set("temp", s.temp == null ? "—" : s.temp + "°"); this.bar("temp", s.temp == null ? 0 : (s.temp - 20) / 60 * 100);
    this.querySelector('[data-v="temp"]').classList.toggle("hot", s.temp >= 70);
    this.set("up", s.host + " · up " + uptime(s.uptime));
    this.set("disk", disk + "%"); this.bar("disk", disk); this.set("disk-sub", gb(s.disk.used) + " / " + gb(s.disk.total) + " GB");
    this.set("model", s.model);
  }
}

export default {
  id: "monitor",
  name: "Monitor",
  said: ["system monitor"],
  icon: I.monitor,
  size: [480, 440],
  launcher: true,
  element: AppMonitor,
};
