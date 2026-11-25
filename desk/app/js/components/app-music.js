// The music player, with the symbios markup and styles (.music): walk the Music folder, pick a
// track, and it plays through the shared media service, so the dock chip stays in sync and
// the music goes on when this window is closed. Covers are dithered in the theme's two colours.
import { bus, list } from "../services/device.js";
import { about } from "../services/changes.js";
import { media, fmt, setQueue, toggle, next, prev, seek, isPlaying, current, position } from "../services/media.js";
import { paintDither, themeColors } from "../dither.js";

const AUDIO_EXT = ["mp3", "flac", "ogg", "oga", "opus", "m4a", "aac", "wav"];
const IMG_EXT = ["jpg", "jpeg", "png", "webp", "gif"];
const ROOT = "Music";
const ext = n => n.split(".").pop().toLowerCase();
const stripExt = n => n.replace(/\.[^.]+$/, "");
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text || "" });

class AppMusic extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="music">
      <div class="bar"><button class="root" title="Music">⌂</button><button class="up" title="Up">↑</button><input class="path" spellcheck="false" readonly aria-label="Folder"></div>
      <div class="list"></div>
      <div class="player"><div class="phead"><canvas class="cover"></canvas>
        <div class="pmeta"><div class="now">Nothing playing</div>
          <div class="ctrls"><button class="prev" aria-label="Previous">|&lt;</button><button class="play" aria-label="Play or pause">&gt;</button><button class="next" aria-label="Next">&gt;|</button><span class="time">0:00 / 0:00</span></div></div></div>
        <div class="seek"><div class="fill"></div></div></div></div>`;
    const q = s => this.querySelector(s);
    this.listEl = q(".list"); this.pathEl = q(".path"); this.nowEl = q(".now"); this.playBtn = q(".play");
    this.timeEl = q(".time"); this.fill = q(".fill"); this.coverEl = q(".cover");
    this.playBtn.addEventListener("click", toggle);
    q(".prev").addEventListener("click", prev);
    q(".next").addEventListener("click", next);
    q(".root").addEventListener("click", () => this.nav(ROOT));
    q(".up").addEventListener("click", () => { if (this.path !== ROOT) this.nav(this.path.split("/").slice(0, -1).join("/")); });
    q(".seek").addEventListener("click", e => { const r = e.currentTarget.getBoundingClientRect(); seek((e.clientX - r.left) / r.width); });
    this.onMedia = () => this.sync();
    this.onPos = () => this.syncPos();
    bus.addEventListener("media", this.onMedia);
    bus.addEventListener("media-pos", this.onPos);
    this.onFiles = e => { if (about(e, "Music")) this.nav(this.path); }; // new tracks: the list only, the player plays on
    bus.addEventListener("files", this.onFiles);
    // open on the album that is playing, if any
    const t = current();
    this.nav(t ? t.path.split("/").slice(0, -1).join("/") : ROOT);
  }
  disconnectedCallback() { bus.removeEventListener("media", this.onMedia); bus.removeEventListener("media-pos", this.onPos); bus.removeEventListener("files", this.onFiles); } // the music goes on
  async nav(path) {
    this.path = path;
    this.pathEl.value = "~/" + path;
    let d;
    try { d = await list(path); }
    catch (e) { return this.listEl.replaceChildren(el("div", "empty", e.message === "not found" ? "There is no Music folder yet. Put albums in ~/Music." : e.message)); }
    const mk = n => path + "/" + n;
    const dirs = d.entries.filter(e => e.dir), tracks = d.entries.filter(e => !e.dir && AUDIO_EXT.includes(ext(e.name)));
    const cover = this.findCover(d.entries, mk);
    this.showCover(cover);
    if (!dirs.length && !tracks.length) return this.listEl.replaceChildren(el("div", "empty", "No folders or audio here."));
    const queue = tracks.map(e => ({ name: stripExt(e.name), path: mk(e.name) }));
    this.listEl.replaceChildren(
      ...dirs.map(e => { const it = this.item("▸", e.name); it.addEventListener("click", () => this.nav(mk(e.name))); return it; }),
      ...tracks.map((e, i) => { const it = this.item("♪", stripExt(e.name)); it.dataset.path = mk(e.name); it.addEventListener("click", () => setQueue(queue, i, cover)); return it; }));
    this.sync();
  }
  item(icon, name) { const it = el("div", "item"); it.append(el("span", "ic", icon), el("span", "nm", name)); return it; }
  findCover(entries, mk) {
    const imgs = entries.filter(e => !e.dir && IMG_EXT.includes(ext(e.name)));
    for (const p of ["cover", "folder", "front", "albumart", "album"]) {
      const m = imgs.find(e => stripExt(e.name).toLowerCase() === p);
      if (m) return mk(m.name);
    }
    return imgs.length ? mk(imgs[0].name) : null;
  }
  showCover(path) {
    this.coverEl.classList.remove("show");
    if (!path) return;
    const img = new Image();
    img.onload = () => { const [fg, bg] = themeColors(); if (paintDither(this.coverEl, img, fg, bg, 192)) this.coverEl.classList.add("show"); };
    img.src = "/api/fs/raw?path=" + encodeURIComponent(path);
  }
  sync() {
    const t = current();
    this.nowEl.textContent = t ? t.name : "Nothing playing";
    this.playBtn.textContent = isPlaying() ? "||" : ">";
    for (const it of this.listEl.querySelectorAll(".item")) it.classList.toggle("playing", !!t && it.dataset.path === t.path && isPlaying());
    this.syncPos();
  }
  syncPos() {
    const { c, d } = position();
    this.fill.style.width = (d ? (c / d) * 100 : 0) + "%";
    this.timeEl.textContent = fmt(c) + " / " + fmt(d);
  }
}
customElements.define("app-music", AppMusic);
