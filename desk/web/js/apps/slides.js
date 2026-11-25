// Slides: the decks in ~/Slides (a folder each, with its PDF); a tap opens one and it takes the whole screen, above
// the dock, the dock hidden; the full-screen button (or F, or Escape) puts it back in its window, where End is.
// Which slide shows is the server's (shared/slides.js): keys here, the phone, or another screen change it, and every
// screen follows. Keys, as a clicker sends them: → PageDown Space next, ← PageUp previous, a number then Enter goes
// there, B or . blacks the screen, F or Escape window / full. Each slide is decoded before it shows, and the next one
// ahead of time, so a change never waits. The old page's app-slides.js, carried over as it was, in the design
// system's pieces only: the app bar, rows, the viewers' .pic; the shell puts the window over the screen (Gab, 24 Nov: "we forgot to port the slide app … it's not living on the board anymore").
import { I } from "../shared/icons.js";
import { home } from "../shared/api.js";
import { el } from "../utils/dom.js";
import { retitle, fullScreen } from "../shared/desk.js";
import { slides, now, steer, decks, deck, picture } from "../shared/slides.js";

const NEXT = ["ArrowRight", "ArrowDown", "PageDown", " "], PREV = ["ArrowLeft", "ArrowUp", "PageUp", "Backspace"];
const EMPTY = "No deck yet. Put a folder with a PDF in ~/Slides: the slides, or the deck exported as notes pages (Google Slides: Print preview, 1 slide with notes).";
// a key typed into a field of another window (the Reader's Edit, TermNL) is that window's, unless the deck fills the screen
const typing = e => !now.full && e.target.closest?.("input, textarea, [contenteditable=''], [contenteditable='true'], .xterm");

class AppSlides extends HTMLElement {
  connectedCallback() {
    if (this.bar) return;
    this.innerHTML = `<div class="app-bar"><span class="grow muted">~/Slides</span><button class="ib" title="Full screen (F)" hidden>${I.full}</button><button class="btn" hidden>End</button></div>
      <div class="app-scroll"><div data-empty=""></div></div>
      <div class="pic" hidden><img alt=""></div>`;
    const q = s => this.querySelector(s);
    this.bar = q(".app-bar"); this.where = q(".grow"); this.fullb = q(".ib"); this.endb = q(".btn");
    this.scroll = q(".app-scroll"); this.listEl = q("[data-empty]"); this.stage = q(".pic"); this.img = q("img");
    this.typed = "";
    this.fullb.onclick = () => { if (!now.full) document.documentElement.requestFullscreen?.().catch(() => {}); steer("full").catch(() => {}); };
    this.endb.onclick = () => steer("end").catch(() => {});
    this.onSlide = () => this.show();
    slides.addEventListener("slide", this.onSlide);
    this.onChange = () => this.load();  // a deck added or made: the list only, never the deck on show
    home.addEventListener("changed", this.onChange);
    this.onKey = e => this.key(e);
    addEventListener("keydown", this.onKey);
    this.addEventListener("mousemove", () => this.pointer());
    this.load();
    this.show();
  }
  closing() {
    slides.removeEventListener("slide", this.onSlide);
    home.removeEventListener("changed", this.onChange);
    removeEventListener("keydown", this.onKey);
    fullScreen(this, false);
  }
  async load() {
    let names, preparing;
    try { ({ names, preparing } = await decks()); }
    catch (e) { this.listEl.dataset.empty = e.message; return this.listEl.replaceChildren(); }
    this.listEl.dataset.empty = EMPTY;
    this.listEl.replaceChildren(...names.map(name => {
      const busy = preparing.includes(name), row = el("div", busy ? "row" : "row link");
      const g = el("span", "g"); g.innerHTML = I.slides;
      row.append(g, el("span", "name", name), el("span", "meta", busy ? "preparing…" : ""));
      if (busy) row.classList.add("muted");  // its slides are being made: not to open yet
      else row.onclick = () => this.open(name, row);
      return row;
    }));
  }
  async open(name, row) {
    // on a laptop on the cable, the browser's own full screen too (it is only allowed on a tap)
    document.documentElement.requestFullscreen?.().catch(() => {});
    row.querySelector(".meta").textContent = "";
    try { await steer("open " + name); }
    catch (e) { row.querySelector(".meta").textContent = e.message; }
  }
  // the slide on show, from the server: the deck's slides once, then each picture decoded before it replaces the last
  async show() {
    const on = !!now.deck, full = on && now.full;
    fullScreen(this, full);
    this.classList.toggle("full", full);  // the pointer hidden until it moves
    this.bar.hidden = full;
    this.fullb.hidden = this.endb.hidden = this.stage.hidden = !on;
    this.scroll.hidden = on;
    this.img.hidden = on && now.black;  // blacked: the stage's own black
    this.where.textContent = on ? `~/Slides/${now.deck}  ${now.i} / ${now.n}` : "~/Slides";
    retitle(this, on ? now.deck : "Slides");
    if (!full && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (!on) { this.shown = null; return; }
    if (this.deck?.title !== now.deck) {
      let d;
      try { d = await deck(now.deck); } catch { return; }  // being prepared, or gone: the next change says
      if (now.deck !== d.title) return;  // another deck was asked for in the meantime
      this.deck = d;
    }
    const want = now.deck + "/" + now.i;
    if (this.shown === want) return;
    const pic = await this.picture(now.i);
    if (now.deck + "/" + now.i !== want) return;  // the slide moved on while this one was decoding
    this.img.src = pic.src;
    this.shown = want;
    if (now.i < now.n) this.picture(now.i + 1);  // ready before it is asked for
  }
  picture(i) {
    const img = new Image();
    img.src = picture(this.deck, i);
    return img.decode().then(() => img, () => img);
  }
  key(e) {
    if (!now.deck || e.ctrlKey || e.altKey || e.metaKey || typing(e)) return;
    let words = null;
    if (/^\d$/.test(e.key)) { this.typed += e.key; return e.preventDefault(); }
    if (e.key === "Enter") words = this.typed ? "go " + this.typed : "next";
    else if (NEXT.includes(e.key)) words = "next";
    else if (PREV.includes(e.key)) words = "prev";
    else if (e.key === "b" || e.key === "B" || e.key === ".") words = "black";
    else if (e.key === "f" || e.key === "F" || (e.key === "Escape" && now.full)) words = "full";
    this.typed = "";
    if (!words) return;
    e.preventDefault();
    steer(words).catch(() => {});
  }
  // the pointer shows while it moves (as a pointer at the slide), and hides again after two seconds
  pointer() {
    this.classList.add("pointing");
    clearTimeout(this.still);
    this.still = setTimeout(() => this.classList.remove("pointing"), 2000);
  }
}

export default {
  id: "slides",
  name: "Slides",
  said: ["slide", "presentation", "slideshow"],
  icon: I.slides,
  size: [420, 360],
  launcher: true,
  element: AppSlides,
};
