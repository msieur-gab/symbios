// Reader: a note, an article, any text, read and written; Markdown drawn by marked (js/lib).
import { clean } from "../../../shared/clean.js";
import { I } from "../../../shared/icons.js";
import { text, call } from "../../../shared/api.js";
import { titled } from "../../../shared/desk.js";
import { markdownBar } from "./markdown-bar.js";

const loadScript = src => new Promise((ok, no) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = no; document.head.append(s); });

// Reader: a note, an article, any text, read; and written (Gab, 23 Nov: "we miss the MD file editor"). Edit shows
// the text itself, Save (or Ctrl+S) writes it (the desk's /api/fs/write: inside the home, kept whole if cut short),
// Done goes back to the page. What was typed is saved before the window closes or another file opens in it.
class AppReader extends HTMLElement {
  async show(item, among, editing) {
    if (this.changed) await this.save();
    this.path = item.path;
    this.item = item;
    titled(this, item);
    if (!this.bar) {
      this.innerHTML = `<div class="read-bar"><span class="read-state muted"></span>
        <button class="btn quiet read-done" hidden>Done</button><button class="btn solid read-save" hidden>Save</button><button class="btn read-edit">Edit</button></div><div class="read-body"></div>`;
      this.bar = this.querySelector(".read-bar");
      this.querySelector(".read-edit").onclick = () => this.edit();
      this.querySelector(".read-save").onclick = () => this.save();
      this.querySelector(".read-done").onclick = async () => { if (this.changed) await this.save(); if (!this.changed) this.read(); };
      this.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); this.save(); } });
    }
    return editing ? this.edit() : this.read();
  }
  state(words) { this.querySelector(".read-state").textContent = words || ""; }
  mode(editing) {
    this.querySelector(".read-edit").hidden = editing;
    this.querySelector(".read-save").hidden = this.querySelector(".read-done").hidden = !editing;
  }
  async read() {
    this.changed = false;
    this.mode(false);
    this.state("");
    const body = this.querySelector(".read-body");
    body.innerHTML = `<div class="read-page"><p class="empty">…</p></div>`;
    const box = body.firstElementChild;
    try {
      const words = await text(this.path);
      if (/\.(md|markdown)$/i.test(this.path)) {
        if (!window.marked) await loadScript("js/lib/marked.min.js");
        // front matter shown as a small card, the rest as the page; nothing in a file may run on the desk
        const m = words.match(/^---\n([\s\S]*?)\n---\n?/);
        const page = clean(window.marked.parse(m ? words.slice(m[0].length) : words)); // shared/clean.js
        const card = m && !this.item.bare;  // bare: the text alone (a memo's header is the board's, not to read)
        box.innerHTML = `<article class="md">${card ? '<pre class="front"></pre>' : ""}</article>`;
        box.firstElementChild.append(page);
        if (card) box.querySelector(".front").textContent = m[1];
      } else {
        box.innerHTML = `<pre class="plain"></pre>`;
        box.firstElementChild.textContent = words;
      }
    } catch (e) { box.innerHTML = `<p class="empty"></p>`; box.firstElementChild.textContent = e.message; }
  }
  async edit() {
    this.mode(true);
    this.state("");
    const body = this.querySelector(".read-body");
    let words = "";
    try { words = await text(this.path); } catch (e) { this.state(e.message); }
    body.innerHTML = `<textarea class="read-write" spellcheck="false" aria-label="The text"></textarea>`;
    this.area = body.firstElementChild;
    // the buttons, for Markdown only, at the window's foot, centred (Gab, 23 Nov: "the toolbar at the bottom of the
    // window and center in the view")
    if (/\.(md|markdown)$/i.test(this.path)) body.append(markdownBar(this.area));
    this.area.value = words;
    this.changed = false;
    this.area.addEventListener("input", () => { this.changed = true; this.state("not saved"); });
    this.area.focus({ preventScroll: true });
  }
  async save() {
    if (!this.changed || !this.area) return;
    try {
      await call("fs/write", { path: this.path, text: this.area.value });
      this.changed = false;
      this.state("saved");
    } catch (e) { this.state("not saved: " + e.message); }
  }
  closing() { if (this.changed) this.save(); }
}

export default {
  id: "reader",
  name: "Reader",
  icon: I.reader,
  size: [660, 620],
  many: true,
  opens: ["note", "article", "text"],
  element: AppReader,
};
