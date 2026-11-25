// The video player, in the Music app's markup and styles (.music .video): walk the Videos folder,
// pick a film, and it plays in the window; FULL gives it the whole screen, above the dock, its
// controls hidden until the pointer moves (EXIT or Escape gives the window back). The picture
// is decoded by whatever device shows the desk; on the board's own screen that is the board, which
// plays WebM (VP8/VP9 with Opus or Vorbis) with the GStreamer plugins install.sh adds.
import { list } from "../services/device.js";
import { fmt, isPlaying, toggle } from "../services/media.js";

const VIDEO_EXT = ["webm", "mp4", "m4v", "ogv", "mkv", "mov"];
const ROOT = "Videos";
const ext = n => n.split(".").pop().toLowerCase();
const stripExt = n => n.replace(/\.[^.]+$/, "");
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text || "" });

class AppVideo extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="music video">
      <div class="bar"><button class="root" title="Videos">⌂</button><button class="up" title="Up">↑</button><input class="path" spellcheck="false" readonly aria-label="Folder"></div>
      <div class="list"></div>
      <video class="screen" preload="metadata" playsinline></video>
      <div class="player"><div class="now">Nothing playing</div>
        <div class="ctrls"><button class="play" aria-label="Play or pause">&gt;</button><button class="back" aria-label="Back 10 seconds">-10</button><button class="fwd" aria-label="Forward 30 seconds">+30</button><button class="films" aria-label="The list">LIST</button><button class="full" aria-label="Full screen">FULL</button><span class="time">0:00 / 0:00</span></div>
        <div class="seek"><div class="fill"></div></div></div></div>`;
    const q = s => this.querySelector(s);
    this.box = q(".video"); this.listEl = q(".list"); this.pathEl = q(".path"); this.nowEl = q(".now"); this.playBtn = q(".play");
    this.timeEl = q(".time"); this.fill = q(".fill"); this.v = q(".screen");
    this.playBtn.addEventListener("click", () => this.toggle());
    this.v.addEventListener("click", () => this.toggle());
    q(".back").addEventListener("click", () => { this.v.currentTime = Math.max(0, this.v.currentTime - 10); });
    q(".fwd").addEventListener("click", () => { this.v.currentTime += 30; });
    q(".films").addEventListener("click", () => { this.fullScreen(false); this.box.classList.toggle("watching"); });
    this.fullBtn = q(".full");
    this.fullBtn.addEventListener("click", () => this.fullScreen(!this.box.classList.contains("full")));
    this.box.addEventListener("mousemove", () => this.reveal());
    this.onKey = e => { if (e.key === "Escape" && this.box.classList.contains("full")) this.fullScreen(false); };
    addEventListener("keydown", this.onKey);
    q(".root").addEventListener("click", () => this.nav(ROOT));
    q(".up").addEventListener("click", () => { if (this.path !== ROOT) this.nav(this.path.split("/").slice(0, -1).join("/")); });
    q(".seek").addEventListener("click", e => { const r = e.currentTarget.getBoundingClientRect(); if (this.v.duration) this.v.currentTime = (e.clientX - r.left) / r.width * this.v.duration; });
    for (const type of ["play", "pause", "loadedmetadata", "ended"]) this.v.addEventListener(type, () => this.sync());
    // the time once a second, not on every tick: on the board's own screen each repaint costs heat
    let lastSec = -1;
    this.v.addEventListener("timeupdate", () => { const s = Math.floor(this.v.currentTime); if (s !== lastSec) { lastSec = s; this.sync(); } });
    this.v.addEventListener("error", () => { this.nowEl.textContent = "This film can't be played here (" + (this.v.error?.message || "unknown format") + ")"; });
    this.nav(ROOT);
  }
  disconnectedCallback() { this.v.pause(); this.v.removeAttribute("src"); this.v.load(); removeEventListener("keydown", this.onKey); document.body.classList.remove("full-screen"); } // closing the window stops the film
  // the whole screen: the window covers the desk and the dock; the controls show while the pointer moves
  fullScreen(on) {
    this.closest("desk-window")?.classList.toggle("full-screen", on);
    document.body.classList.toggle("full-screen", on);
    this.box.classList.toggle("full", on);
    this.fullBtn.textContent = on ? "EXIT" : "FULL";
    if (on) { this.box.classList.add("watching"); this.reveal(); }
  }
  reveal() {
    if (!this.box.classList.contains("full")) return;
    this.box.classList.add("show");
    clearTimeout(this.hide);
    this.hide = setTimeout(() => this.box.classList.remove("show"), 3000);
  }
  async nav(path) {
    this.path = path;
    this.pathEl.value = "~/" + path;
    this.box.classList.remove("watching");
    let d;
    try { d = await list(path); }
    catch (e) { return this.listEl.replaceChildren(el("div", "empty", e.message === "not found" ? "There is no Videos folder yet. Put films in ~/Videos." : e.message)); }
    const mk = n => path + "/" + n;
    const dirs = d.entries.filter(e => e.dir), films = d.entries.filter(e => !e.dir && VIDEO_EXT.includes(ext(e.name)));
    if (!dirs.length && !films.length) return this.listEl.replaceChildren(el("div", "empty", "No folders or films here."));
    this.listEl.replaceChildren(
      ...dirs.map(e => { const it = this.item("▸", e.name); it.addEventListener("click", () => this.nav(mk(e.name))); return it; }),
      ...films.map(e => { const it = this.item("▶", stripExt(e.name)); it.dataset.path = mk(e.name); it.addEventListener("click", () => this.play(mk(e.name), stripExt(e.name))); return it; }));
    this.sync();
  }
  item(icon, name) { const it = el("div", "item"); it.append(el("span", "ic", icon), el("span", "nm", name)); return it; }
  play(path, name) {
    if (isPlaying()) toggle(); // the music pauses: one sound at a time
    this.film = { path, name };
    this.v.src = "/api/fs/raw?path=" + encodeURIComponent(path);
    this.v.play().catch(() => this.sync());
    this.box.classList.add("watching");
    this.sync();
  }
  toggle() {
    if (!this.film) return;
    if (this.v.paused) { if (isPlaying()) toggle(); this.v.play().catch(() => {}); } else this.v.pause();
  }
  sync() {
    this.nowEl.textContent = this.film ? this.film.name : "Nothing playing";
    this.playBtn.textContent = this.film && !this.v.paused ? "||" : ">";
    for (const it of this.listEl.querySelectorAll(".item")) it.classList.toggle("playing", !!this.film && it.dataset.path === this.film.path);
    const c = this.v.currentTime || 0, d = this.v.duration || 0;
    this.fill.style.width = (d ? (c / d) * 100 : 0) + "%";
    this.timeEl.textContent = fmt(c) + " / " + fmt(d);
  }
}
customElements.define("app-video", AppVideo);
