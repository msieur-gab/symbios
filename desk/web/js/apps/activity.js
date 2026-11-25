// Activity: one line per task on the board, a plain bar and the time left; queued tasks say "pending", a finished
// one says "done" for a moment and goes (decided with Gab, 2026-10-19). The tasks are the board's own (changes.js,
// signals.py): a memo transcribed, an article or memo made searchable, a deck made. The old System window's
// Activity section, carried over as it was into an app of its own (the fold; Gab, 23 Nov: "the activity should
// become an app in the app registry"), and shown by the Monitor under its gauges, the same element.
import { I } from "../shared/icons.js";
import { bus, tasks, skew } from "../shared/changes.js";

const left = s => s >= 90 ? Math.round(s / 60) + " min" : Math.max(1, Math.round(s)) + " s";

class AppActivity extends HTMLElement {
  // one element wherever it is shown: its own window (the loader), or under the Monitor's four gauges (monitor.js),
  // as decided on 19 Oct (Gab, 23 Nov: "it's not two different codes in two different places, it becomes just one")
  connectedCallback() {
    if (!this.tasks) {
      this.innerHTML = `<div class="app-scroll"><div class="tasks"></div></div>`;  // the app layer: no style of its own
      this.tasks = this.querySelector(".tasks");
      this.rows = new Map();
      this.onTasks = () => this.activity();
    }
    bus.addEventListener("tasks", this.onTasks);
    this.activity();
  }
  disconnectedCallback() { bus.removeEventListener("tasks", this.onTasks); clearTimeout(this.soon); }
  // the board's heavy work as signals.py tells it; a line is added or removed only when a task arrives or ends,
  // the rest is a bar's transform and a text change. A task that tells how much is done shows that and its pace's
  // time left; one with only an expected length shows the clock against it ("almost" past it); one with neither
  // shows its bar empty and "running"
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
      const run = t.state === "running", gone = run ? now - t.since : 0, told = run && t.done != null;
      // a job that tells how much it has done (a memo: how far the model has read) moves by that alone, and its
      // time left is its own pace so far; it stops where the model stops (Gab, 24 Nov: "the progress should be real")
      const pct = t.ended ? 100 : told ? Math.min(99, t.done * 100) : run && t.expect ? Math.min(99, (gone / t.expect) * 100) : 0;
      row.className = "work" + (t.state === "pending" ? " pending" : "");
      row.querySelector(".name").textContent = t.name;
      row.querySelector("i").style.transform = "scaleX(" + pct / 100 + ")";
      row.querySelector(".time").textContent = t.state === "done" ? "done" : t.state === "failed" ? "failed" : !run ? "pending"
        : told ? (t.done > 0 ? Math.round(t.done * 100) + "% · " + left(gone * (1 - t.done) / t.done) : "starting")
        : !t.expect ? "running" : t.expect - gone > 1 ? left(t.expect - gone) : "almost";
    }
    for (const [id, row] of this.rows) if (!seen.has(id)) { row.remove(); this.rows.delete(id); }
    this.tasks.dataset.empty = "Nothing running.";
    if (this.rows.size) this.soon = setTimeout(() => this.activity(), 1000); // the bars move while there is work
  }
}

export default {
  id: "activity",
  name: "Activity",
  said: ["notifications"],
  icon: I.activity,
  size: [560, 320],
  launcher: true,
  element: AppActivity,
};
