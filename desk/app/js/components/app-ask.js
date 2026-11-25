// Ask: a question to the board's articles and memos, answered by meaning and keywords (ask.py on the board), or
// "not here" when nothing is close enough (Gab, 2026-10-23). A chat like the Assistant's ("make it look more like the
// ptiLU chat"): the question on one side, the answer on the other with the documents in it, examples as chips. A
// document opens where it is read: an article in the Reader, a memo's transcript in the Editor.
import { bus, ask } from "../services/device.js";

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text || "" });
const log = []; // the conversation outlives the window, as the Assistant's does
const EXAMPLES = ["does AI impact democracy?", "what is designing by abstention?", "small language models on a Raspberry Pi"];

class AppAsk extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="pane" aria-live="polite"></div>
      <div class="chips"></div>
      <form class="entry"><input name="q" placeholder="Ask your articles and memos: does AI impact democracy?" autocomplete="off" spellcheck="false" aria-label="Question"><button>Ask</button></form>`;
    this.list = this.querySelector(".pane");
    for (const node of log) this.list.append(node);
    for (const q of EXAMPLES) this.querySelector(".chips").append(el("button", "", q));
    this.querySelector(".chips").addEventListener("click", e => { if (e.target.tagName === "BUTTON") this.ask(e.target.textContent); });
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const q = e.target.q;
      if (q.value.trim()) this.ask(q.value.trim());
      q.value = "";
    });
    this.querySelector("input").focus({ preventScroll: true });
  }
  add(...nodes) {
    log.push(...nodes);
    this.list.append(...nodes);
    this.list.scrollTop = this.list.scrollHeight;
  }
  async ask(q) {
    const bubble = el("div", "it", "Looking through your articles and memos…");
    this.add(el("div", "me", q), bubble);
    let a;
    try { a = await ask(q); } catch (e) { bubble.textContent = "The board can't answer: " + e.message + "."; return; }
    if (!a.results.length) {
      bubble.textContent = "Nothing in your articles or memos is close enough to that." + (a.best != null ? " (best " + a.best.toFixed(2) + ", needs " + a.floor.toFixed(2) + ")" : "");
      return;
    }
    bubble.textContent = a.results.length > 1 ? a.results.length + " documents are about it:" : "One document is about it:";
    for (const r of a.results) {
      const row = el("button", "hit");
      row.type = "button";
      const top = el("div", "top");
      top.append(el("span", "score", r.score.toFixed(2)), el("span", "title", r.title), el("span", "kind", r.kind));
      row.append(top, el("div", "passage", r.passage));
      row.addEventListener("click", () => bus.dispatchEvent(new CustomEvent("open", { detail: { app: r.kind === "memo" ? "editor" : "reader", path: r.path } })));
      bubble.append(row);
    }
    this.list.scrollTop = this.list.scrollHeight;
  }
}
customElements.define("app-ask", AppAsk);
