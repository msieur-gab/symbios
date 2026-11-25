// The assistant: say something, see the reply, and under it the command and what became of it.
// TermNL answers, on the device (the desk server's /api/say); what the page does itself (a file to
// open, later the sound and the light) comes back as "screen" and goes through run().
import { bus, article, say, run, noted } from "../services/device.js";
import { I } from "../icons.js";

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text || "" });
export const commandLine = r => { const c = el("div", "cmd", r.command); if (r.how) c.dataset.how = r.how; if (r.why) c.title = r.why; return c; };
const log = []; // the conversation outlives the window
const session = (() => { try { return crypto.randomUUID(); } catch { return "s" + Math.random().toString(36).slice(2); } })();
// a few things to say, under the conversation: all reading, so a tap changes nothing (each answered at once by TermNL)
const SHORTCUTS = ["show my files", "how much space is left", "how much memory is left", "how hot is the board",
  "is the wifi working", "what is my ip", "check bluetooth", "what's running"];
const HOW = { ran: "ran", read: "ran", simulated: "simulated", failed: "failed" }; // TermNL's word → the desk's

class AppAssistant extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="pane" aria-live="polite"></div>
      <div class="chips"></div>
      <form class="entry"><input name="q" placeholder="Say something: make a folder called drafts" autocomplete="off" aria-label="Command"><button>Send</button></form>`;
    this.list = this.querySelector(".pane");
    for (const node of log) this.list.append(node);
    for (const s of SHORTCUTS) this.querySelector(".chips").append(el("button", "", s));
    this.querySelector(".chips").addEventListener("click", e => { if (e.target.tagName === "BUTTON") this.say(e.target.textContent); });
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const q = e.target.q;
      if (q.value.trim()) this.say(q.value.trim());
      q.value = "";
    });
    this.querySelector("input").focus({ preventScroll: true });
  }
  add(...nodes) {
    log.push(...nodes);
    this.list.append(...nodes);
    this.list.scrollTop = this.list.scrollHeight;
  }
  async say(text) {
    // the question those chips answered is over: an old chip can't be tapped again
    for (const b of this.list.querySelectorAll(".it button.chip")) b.disabled = true;
    this.add(el("div", "me", text));
    const link = /https?:\/\/\S+/.exec(text);
    if (link) return this.keep(link[0]); // a link is not a sentence: the board keeps its article
    let r;
    try { r = await say(text, session); } catch (e) { return this.add(el("div", "it", "I can't reach TermNL: " + e.message + ".")); }
    const bubble = el("pre", "it", r.say);
    if (r.table) bubble.append(this.table(r.table));
    for (const d of r.documents || []) bubble.append(this.document(d)); // TermNL didn't know it; the articles and memos did
    if (r.chips?.length) {
      const chips = el("div", "answers");
      for (const c of r.chips) {
        const b = el("button", "chip", c);
        b.type = "button";
        b.addEventListener("click", () => this.say(c));
        chips.append(b);
      }
      bubble.append(chips);
    }
    const lines = [];
    if (r.screen) { // the page does it: a window opens, the player plays
      const done = await run(r.screen);
      if (done.reply) bubble.textContent = done.reply; // the player says what really happened ("I found nothing called…")
      lines.push(commandLine(done));
    }
    else if (r.show && r.outcome === "approve") lines.push(commandLine({ command: r.show })); // what would run
    else if (r.show && HOW[r.ran]) {
      const entry = { command: r.show, how: HOW[r.ran], out: r.output || "" };
      noted(entry); // the Terminal window shows it too; the raw output is its business, not the conversation's
      lines.push(commandLine(entry));
    }
    this.add(bubble, ...lines);
  }
  // an article or memo, as in the Ask window: a tap opens it where it is read (an article in the Reader, a memo in the Editor)
  document(d) {
    const row = el("button", "hit");
    row.type = "button";
    const top = el("div", "top");
    top.append(el("span", "score", d.score.toFixed(2)), el("span", "title", d.title), el("span", "kind", d.kind));
    row.append(top, el("div", "passage", d.passage));
    row.addEventListener("click", () => bus.dispatchEvent(new CustomEvent("open", { detail: { app: d.kind === "memo" ? "editor" : "reader", path: d.path } })));
    return row;
  }
  // a reader's table: its columns, then its rows; a row's level (weak, hot…) marks its last cell, a row's mark
  // (lock: a Wi-Fi network that asks for a password) is drawn before its first (Gab, 25 Oct: "Simple shape and one color")
  table({ columns, rows, levels = [], marks = [] }) {
    const t = document.createElement("table");
    const head = t.createTHead().insertRow();
    for (const c of columns) head.append(el("th", "", c));
    rows.forEach((row, i) => {
      const tr = t.insertRow();
      row.forEach((v, j) => { const td = tr.insertCell(); td.textContent = v; if (levels[i] && j === row.length - 1) td.dataset.level = levels[i]; });
      if (marks[i] === "lock") { const m = el("span", "mark"); m.innerHTML = I.lock; tr.cells[0].prepend(m); }
    });
    return t;
  }
  // a web address → the board reads the page and keeps the article as markdown in Articles
  async keep(url) {
    const bubble = el("div", "it", "Reading that page…");
    this.add(bubble);
    try {
      const a = await article(url);
      bubble.textContent = `Kept “${a.title}” (${a.words} words) in Articles. `;
      const open = el("button", "", "Read");
      open.addEventListener("click", () => bus.dispatchEvent(new CustomEvent("open", { detail: { app: "reader", path: a.path } })));
      bubble.append(open);
    } catch (e) {
      bubble.textContent = "Not kept: " + e.message + ".";
    }
  }
}
customElements.define("app-assistant", AppAssistant);
