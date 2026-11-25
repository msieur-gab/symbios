// TermNL's two windows, from the desk (desk/app/js/components/app-assistant.js, app-terminal.js), dressed in
// the design system. TermNL (the old page called it the Assistant; Gab, 23 Nov: "what you call assistant is actually
// termNL"): say something, TermNL answers on the device and runs its skills' commands;
// under each reply, the command and what became of it. The Terminal: a real bash near the board (its screen, its
// cable), and the log of every command of this session (Gab, 23 Nov: "see how terminal will cope with it").
import { I } from "../../../shared/icons.js";
import { start } from "../../../shared/desk.js";
import { el } from "../../../utils/dom.js";
import { appPref, setAppPref, prefs } from "../../../shared/prefs.js";
import { row, toggle, section } from "../../../shared/controls.js";
import { api, run, noted, commandLine, own } from "./commands.js";

// ---- TermNL ----
const SHORTCUTS = ["show my files", "how much space is left", "how much memory is left", "how hot is the board",
  "is the wifi working", "what is my ip", "check bluetooth", "what's running"];
const HOW = { ran: "ran", read: "ran", simulated: "simulated", failed: "failed" };
const said = []; // the conversation outlives the window
// the sentences offered under the box, or not (Settings)
const suggesting = () => appPref("termnl", "suggestions", true);
const session = (() => { try { return crypto.randomUUID(); } catch { return "s" + Math.random().toString(36).slice(2); } })();

class AppTermNL extends HTMLElement {
  connectedCallback() {
    if (this.list) return;
    this.innerHTML = `<div class="tn-talk" aria-live="polite"></div>
      <div class="tn-short"></div>
      <form class="tn-entry"><input class="field" name="q" placeholder="Say something: make a folder called drafts" autocomplete="off" aria-label="Say"><button class="btn solid">Send</button></form>`;
    this.list = this.querySelector(".tn-talk");
    if (!said.length) this.list.append(el("p", "tn-hello muted read", "TermNL answers here, on the board. Ask it about the board, or to do something with your files."));
    for (const n of said) this.list.append(n);
    const short = this.querySelector(".tn-short");
    short.hidden = !suggesting();
    this.onPrefs = e => { if (e.detail.key === "app.termnl") short.hidden = !suggesting(); };
    prefs.addEventListener("change", this.onPrefs);
    for (const s of SHORTCUTS) { const b = el("button", "chip", s); b.type = "button"; short.append(b); }
    short.addEventListener("click", e => { if (e.target.tagName === "BUTTON") this.say(e.target.textContent); });
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const q = e.target.q;
      if (q.value.trim()) this.say(q.value.trim());
      q.value = "";
    });
    requestAnimationFrame(() => this.querySelector("input").focus({ preventScroll: true }));
  }
  closing() { prefs.removeEventListener("change", this.onPrefs); }
  add(...nodes) {
    this.querySelector(".tn-hello")?.remove();
    said.push(...nodes);
    this.list.append(...nodes);
    this.list.scrollTop = this.list.scrollHeight;
  }
  async say(text) {
    for (const b of this.list.querySelectorAll(".tn-it .chip")) b.disabled = true; // an old question's answers
    this.add(el("div", "tn-me", text));
    const link = /https?:\/\/\S+/.exec(text);
    if (link) return this.keep(link[0]);
    const wait = el("div", "tn-it muted", "…");
    this.add(wait);
    let r;
    try { r = await api("/api/say", { text, session, ...own() }); }
    catch (e) { wait.textContent = "I can't reach TermNL: " + e.message + "."; return; }
    wait.remove();
    said.splice(said.indexOf(wait), 1);
    const bubble = el("div", "tn-it");
    bubble.append(el("div", "tn-say read", r.say));
    if (r.table) bubble.append(this.table(r.table));
    for (const d of r.documents || []) bubble.append(this.document(d));
    if (r.chips?.length) {
      const chips = el("div", "tn-answers");
      for (const c of r.chips) {
        const b = el("button", "chip", c);
        b.type = "button";
        b.addEventListener("click", () => this.say(c));
        chips.append(b);
      }
      bubble.append(chips);
    }
    const lines = [];
    if (r.opens === "settings") start("settings");  // TermNL's switches and the person's name live in the desk's Settings
    if (r.screen) {
      const done = await run(r.screen);
      if (done.reply) bubble.querySelector(".tn-say").textContent = done.reply; // the player says what really happened
      lines.push(commandLine(done));
    }
    else if (r.show && r.outcome === "approve") lines.push(commandLine({ command: r.show }));
    else if (r.show && HOW[r.ran]) {
      const entry = { command: r.show, how: HOW[r.ran], out: r.output || "" };
      noted(entry);
      lines.push(commandLine(entry));
    }
    this.add(bubble, ...lines);
  }
  table({ columns, rows, levels = [], marks = [] }) {
    const t = el("table", "tn-table num");
    const head = t.createTHead().insertRow();
    for (const c of columns) head.append(el("th", "eyebrow", c));
    rows.forEach((row, i) => {
      const tr = t.insertRow();
      row.forEach((v, j) => { const td = tr.insertCell(); td.textContent = v; if (levels[i] && j === row.length - 1) td.dataset.level = levels[i]; });
      if (marks[i] === "lock") { const m = el("span", "tn-mark"); m.innerHTML = I.lock; tr.cells[0].prepend(m); }
    });
    return t;
  }
  document(d) {
    const row = el("button", "row tn-doc");
    row.type = "button";
    row.append(el("span", "meta num", d.score.toFixed(2)), el("span", "name", d.title), el("span", "meta", d.kind));
    row.title = d.passage;
    row.addEventListener("click", () => document.dispatchEvent(new CustomEvent("desk:open", { detail: { item: d.kind === "memo" ? { path: d.path, audio: d.audio, name: d.title, kind: "memo" } : { path: d.path, name: d.title, kind: "article" } } })));
    return row;
  }
  async keep(url) {
    const bubble = el("div", "tn-it", "Reading that page…");
    this.add(bubble);
    try {
      const a = await api("/api/articles", { url });
      bubble.textContent = `Kept “${a.title}” (${a.words} words) in Articles.`;
    } catch (e) { bubble.textContent = "Not kept: " + e.message + "."; }
  }
}

export default {
  id: "termnl",
  name: "TermNL",
  icon: I.termnl,
  size: [460, 560],
  launcher: true,
  dock: true,
  element: AppTermNL,
  settings: () => [section("Suggestions", [row("Sentences to try", "Under the box: \u201cshow my files\u201d, \u201chow hot is the board\u201d\u2026",
    toggle("Suggestions", suggesting(), on => setAppPref("termnl", "suggestions", on)))])],
};
