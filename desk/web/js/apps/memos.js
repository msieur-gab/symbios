// Memos: the voice memos the phone sends (its recorder, "keep for the desk"), each a folder in ~/Memos with its
// sound and the text the board writes (voice.py). The list as the phone's Player shows them: newest first, the
// title, the date and the length, and the first words; "transcribing…" while the board writes them. Play sends a
// memo to the Player (as Files does, the other memos queued after it); opening one shows its text in the Reader,
// inside this window, with its Edit. Made of the design system's pieces only (Gab, 23 Nov: "the one with the voice
// memo, which is also very important").
import { I } from "../shared/icons.js";
import { items, home } from "../shared/api.js";
import { time } from "../utils/format.js";
import { el } from "../utils/dom.js";
import { start } from "../shared/desk.js";

const writing = m => /^\*?Transcribing/i.test(m.text || "");
const titleOf = m => m.name || "Memo, " + (m.date || "");

class AppMemos extends HTMLElement {
  connectedCallback() {
    if (this.memos) return;
    this.memos = [];
    this.onChange = () => this.load();  // a memo arrived, or its text is written (changes.js)
    home.addEventListener("changed", this.onChange);
    this.list();
  }
  closing() { home.removeEventListener("changed", this.onChange); this.reader?.closing?.(); }

  // ---- the list ----
  list() {
    this.reader?.closing?.();
    this.reader = null;
    this.innerHTML = `<div class="app-bar"><span class="grow muted">Voice memos</span></div>
      <div class="app-scroll"><div class="memo-list" data-empty="No memos yet. Record one on the phone and keep it for the desk: it comes here with its text."></div></div>`;
    this.load();
  }
  async load() {
    const box = this.querySelector(".memo-list");
    if (!box) return this.open?.path && this.refresh();
    try { this.memos = (await items("Memos")).filter(i => i.kind === "memo").sort((a, b) => String(b.date || "").localeCompare(String(a.date || ""))); }
    catch (e) { box.dataset.empty = e.message; this.memos = []; }
    this.querySelector(".app-bar .grow").textContent = "Voice memos" + (this.memos.length ? " · " + this.memos.length : "");
    box.replaceChildren(...this.memos.map(m => this.row(m)));
  }
  row(m) {
    const row = el("div", "row link");
    const g = el("span", "g"); g.innerHTML = I.memo;
    const name = el("span", "name", titleOf(m));
    name.append(el("small", "", writing(m) ? "" : m.text || ""));
    const meta = el("span", "meta", writing(m) ? "transcribing…" : [m.date, time(m.duration)].filter(Boolean).join(" · "));
    const play = el("button", "ib", ""); play.innerHTML = I.play; play.title = "Play";
    play.onclick = e => { e.stopPropagation(); this.play(m); };
    row.append(g, name, meta, play);
    row.onclick = () => this.openMemo(m);
    return row;
  }
  play(m) {  // the Player shows each memo by the title shown here ("Memo, <date>" when it has none yet)
    const named = this.memos.map(x => ({ ...x, name: titleOf(x) }));
    start("player", named.find(x => x.path === m.path) || { ...m, name: titleOf(m) }, named);
  }

  // what the desk hands the app when it opens it (shell/loader.js): nothing (the list), or a memo to open
  show(item) { if (item?.kind === "memo") this.openMemo(item); }

  // ---- one memo: its text, in the Reader ----
  openMemo(m) {
    this.open = m;
    this.innerHTML = `<div class="app-bar"><button class="btn quiet back">← Memos</button><span class="grow"></span><span class="meta muted"></span><button class="ib play" title="Play">${I.play}</button></div>`;
    this.querySelector(".grow").textContent = titleOf(m);
    this.querySelector(".meta").textContent = [m.date, time(m.duration)].filter(Boolean).join(" · ");
    this.querySelector(".back").onclick = () => this.list();
    this.querySelector(".play").onclick = () => this.play(m);
    this.reader = Object.assign(document.createElement("app-reader"), { className: "app-part" });
    this.append(this.reader);
    this.reader.show({ path: m.path + "/transcript.md", name: titleOf(m), kind: "note", bare: true });
  }
  refresh() {}  // one memo open: the Reader keeps what is being read or written
}

export default {
  id: "memos",
  name: "Memos",
  said: ["voice memos", "memo"],
  icon: I.memo,
  size: [480, 560],
  launcher: true,
  element: AppMemos,
};
