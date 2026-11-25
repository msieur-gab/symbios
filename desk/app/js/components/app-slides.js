// Slides: the decks in ~/Slides (a folder each, with its PDF), in the Music app's markup and
// styles; a tap opens one and it takes the whole screen, above the dock, as Video's FULL does;
// WINDOW (or F, or Escape) puts it back in its window, where FULL and END are.
// Which slide shows is the server's (services/slides.js): keys here, the phone, or another screen
// change it, and every screen follows. Keys, as a clicker sends them: → PageDown Space next,
// ← PageUp previous, a number then Enter goes there, B or . blacks the screen, F or Escape window / full.
// Each slide is decoded before it shows, and the next one ahead of time, so a change never waits.
import { bus } from "../services/device.js";
import { now, steer, decks, deck } from "../services/slides.js";
import { about } from "../services/changes.js";

const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text || "" });
const NEXT = ["ArrowRight", "ArrowDown", "PageDown", " "], PREV = ["ArrowLeft", "ArrowUp", "PageUp", "Backspace"];

class AppSlides extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="music slides">
      <div class="bar"><input class="path" value="~/Slides" spellcheck="false" readonly aria-label="Folder"><button class="fullb">FULL</button><button class="endb">END</button></div>
      <div class="list"></div>
      <div class="stage"><img class="slide" alt=""><div class="black"></div></div></div>`;
    const q = s => this.querySelector(s);
    this.box = q(".slides"); this.listEl = q(".list"); this.img = q(".slide");
    this.typed = "";
    q(".fullb").addEventListener("click", () => { document.documentElement.requestFullscreen?.().catch(() => {}); steer("full").catch(() => {}); });
    q(".endb").addEventListener("click", () => steer("end").catch(() => {}));
    this.onSlide = () => this.show();
    bus.addEventListener("slide", this.onSlide);
    this.onFiles = e => { if (about(e, "Slides")) this.load(); }; // a deck added or made: the list only, never the deck on show
    bus.addEventListener("files", this.onFiles);
    this.onKey = e => this.key(e);
    addEventListener("keydown", this.onKey);
    this.box.addEventListener("mousemove", () => this.pointer());
    this.load();
    this.show();
  }
  disconnectedCallback() {
    bus.removeEventListener("slide", this.onSlide);
    bus.removeEventListener("files", this.onFiles);
    removeEventListener("keydown", this.onKey);
    document.body.classList.remove("full-screen");
  }
  async load() {
    let names, preparing;
    try { ({ names, preparing } = await decks()); } catch (e) { return this.listEl.replaceChildren(el("div", "empty", e.message)); }
    if (!names.length) return this.listEl.replaceChildren(el("div", "empty", "No deck yet. Put a folder with a PDF in ~/Slides: the slides, or the deck exported as notes pages (Google Slides: Print preview, 1 slide with notes)."));
    this.listEl.replaceChildren(...names.map(name => {
      const it = el("div", "item"), busy = preparing.includes(name);
      it.append(el("span", "ic", "▸"), el("span", "nm", busy ? name + " (preparing…)" : name));
      if (busy) it.style.opacity = 0.5; // its slides are being made: not to open yet
      else it.addEventListener("click", () => this.open(name, it));
      return it;
    }));
  }
  async open(name, it) {
    // on a laptop on the cable, the browser's own full screen too (it is only allowed on a tap)
    document.documentElement.requestFullscreen?.().catch(() => {});
    try { await steer("open " + name); }
    catch (e) { it.querySelector(".nm").textContent = name + " — " + e.message; return; }
    it.querySelector(".nm").textContent = name;
  }
  // the slide on show, from the server: the deck's slides once, then each picture decoded before it replaces the last
  async show() {
    const on = !!now.deck, full = on && now.full;
    this.closest("desk-window")?.classList.toggle("full-screen", full);
    document.body.classList.toggle("full-screen", full);
    this.box.classList.toggle("on", on);
    this.box.classList.toggle("full", full);
    this.box.classList.toggle("blacked", on && now.black);
    this.querySelector(".path").value = on ? "~/Slides/" + now.deck + "  " + now.i + " / " + now.n : "~/Slides";
    if (!full && document.fullscreenElement) document.exitFullscreen().catch(() => {});
    if (!on) { this.shown = null; return; }
    if (this.deck?.title !== now.deck) {
      const d = await deck(now.deck);
      if (now.deck !== d.title) return; // another deck was asked for in the meantime
      this.deck = d;
    }
    const want = now.deck + "/" + now.i;
    if (this.shown === want) return;
    const pic = await this.picture(now.i);
    if (now.deck + "/" + now.i !== want) return; // the slide moved on while this one was decoding
    this.img.src = pic.src;
    this.shown = want;
    if (now.i < now.n) this.picture(now.i + 1); // ready before it is asked for
  }
  picture(i) {
    const img = new Image();
    img.src = "/api/fs/raw?path=" + encodeURIComponent(this.deck.path + String(i).padStart(2, "0") + ".jpg");
    return img.decode().then(() => img, () => img);
  }
  key(e) {
    if (!now.deck || e.ctrlKey || e.altKey || e.metaKey) return;
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
    this.box.classList.add("pointing");
    clearTimeout(this.still);
    this.still = setTimeout(() => this.box.classList.remove("pointing"), 2000);
  }
}
customElements.define("app-slides", AppSlides);
