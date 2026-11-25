// The Player: any sound of the home, wherever it lives (Gab, 1 Nov: the old player "is completely connected
// to the music folder and does not act yet as a standalone music/audio player"). Its queue is the sounds
// of the folder it was opened from; the folder's picture (cover.jpg…) is shown when there is one.
// Opened with nothing playing, it shows the music, artists then albums then tracks, as the old desk's Music app
// walked ~/Music; the music button brings that list back at any time (Gab, 23 Nov: "when I open the music player,
// it's empty, so it don't consider that the music should be part of its own content").
import { I, glyph } from "../../shared/icons.js";
import { raw, items } from "../../shared/api.js";
import { readMemo } from "../../shared/kinds.js";
import { time } from "../../utils/format.js";
import { retitle } from "../../shared/desk.js";

const AUDIO = new Set(["track", "episode", "memo"]);
const COVERS = /^(cover|folder|front|albumart|album)\b/i;
const FOLDERISH = new Set(["folder", "album", "artist", "show"]);
const MUSIC = "Music";

class AppPlayer extends HTMLElement {
  connectedCallback() {
    if (this.audio) return;
    this.innerHTML = `<div class="pl-art"></div>
      <div class="pl-now"><b></b><small></small></div>
      <div class="pl-seek"><span class="pl-t">0:00</span><input type="range" min="0" max="1000" value="0" aria-label="Position"><span class="pl-d">0:00</span></div>
      <div class="pl-ctrl"><button class="ib prev" title="Previous">${I.prev}</button><button class="ib big pp" title="Play or pause">${I.play}</button><button class="ib next" title="Next">${I.next}</button><button class="ib readm" title="Read its text" hidden>${I.reader}</button><button class="ib browse" title="Your music">${I.album}</button></div>
      <ol class="pl-queue"></ol><audio preload="metadata"></audio>`;
    this.audio = this.querySelector("audio");
    const seek = this.querySelector("input");
    this.querySelector(".pp").onclick = () => this.audio.paused ? this.audio.play() : this.audio.pause();
    this.querySelector(".prev").onclick = () => this.queue && this.audio.currentTime > 3 ? (this.audio.currentTime = 0) : this.play(this.at - 1);
    this.querySelector(".next").onclick = () => this.play(this.at + 1);
    this.querySelector(".readm").onclick = () => { const t = this.queue?.[this.at]; if (t?.kind === "memo") readMemo(t); };
    // the folder being walked, or the one the sound playing came from, or Music
    this.querySelector(".browse").onclick = () => {
      const t = this.queue?.[this.at], from = t?.path.includes("/") ? t.path.slice(0, t.path.lastIndexOf("/")) : "";
      this.browse(this.walking || (from.startsWith(MUSIC) ? from : MUSIC));
    };
    seek.oninput = () => { if (Number.isFinite(this.audio.duration)) this.audio.currentTime = seek.value / 1000 * this.audio.duration; };
    this.audio.ontimeupdate = () => {
      // the file's own length; when it has none (a recording that wasn't made whole), the one the board knows
      const d = Number.isFinite(this.audio.duration) ? this.audio.duration : this.queue?.[this.at]?.duration || 0;
      if (d && document.activeElement !== seek) seek.value = this.audio.currentTime / d * 1000;
      this.querySelector(".pl-t").textContent = time(this.audio.currentTime) || "0:00";
      this.querySelector(".pl-d").textContent = time(d) || "0:00";
    };
    this.audio.onloadedmetadata = () => this.audio.ontimeupdate();  // its length shown as soon as it is known, before it plays
    this.audio.onplay = this.audio.onpause = () => { this.querySelector(".pp").innerHTML = this.audio.paused ? I.play : I.pause; this.tell(); };
    this.audio.onended = () => this.at < this.queue.length - 1 && this.play(this.at + 1);
    this.audio.onerror = () => { this.querySelector(".pl-now small").textContent = "This sound can't be played here."; };
  }
  closing() { this.audio.pause(); this.audio.removeAttribute("src"); this.queue = null; this.tell(); }
  // what is playing, for the right island's chip (main.js)
  tell() {
    const t = this.queue?.[this.at];
    document.dispatchEvent(new CustomEvent("desk:media", { detail: t ? { name: t.name, playing: !this.audio.paused } : null }));
  }
  get path() { return this.queue?.[this.at]?.path; }
  show(item, among) {
    if (!item) {  // opened from the dock or the launcher: nothing chosen yet, the music to choose from
      if (this.queue) return;
      this.querySelector(".pl-now b").textContent = "Nothing playing";
      this.querySelector(".pl-now small").textContent = "Choose something below";
      this.querySelector(".pl-art").innerHTML = I.track;
      this.browse(MUSIC);
      return;
    }
    this.walking = null;
    const list = (among || [item]).filter(i => AUDIO.has(i.kind));
    this.queue = list.length ? list : [item];
    const pics = (among || []).filter(i => i.kind === "picture");
    this.cover = (pics.find(p => COVERS.test(p.path.split("/").pop())) || pics[0])?.path;
    this.querySelector(".pl-queue").classList.remove("walking");
    this.querySelector(".pl-queue").replaceChildren(...this.queue.map((t, n) => {
      const li = document.createElement("li");
      li.className = "row link";
      li.append(Object.assign(document.createElement("span"), { className: "name", textContent: t.name }));
      li.onclick = () => this.play(n);
      return li;
    }));
    this.play(Math.max(0, this.queue.findIndex(i => i.path === item.path)));
  }
  // the music, a folder at a time (Music, an artist, an album): its folders to open, its sounds to play, the way up
  async browse(path) {
    this.walking = path;
    const list = this.querySelector(".pl-queue");
    let got;
    try { got = await items(path); } catch {
      list.replaceChildren(Object.assign(document.createElement("li"), { className: "empty", textContent: path === MUSIC ? "There is no Music folder yet." : "This folder can't be read." }));
      return;
    }
    if (this.walking !== path) return;  // another folder was asked for meanwhile
    const row = (glyph, name, meta, go) => {
      const li = document.createElement("li");
      li.className = "row link walk";
      li.innerHTML = `<span class="g">${glyph}</span>`;
      li.append(Object.assign(document.createElement("span"), { className: "name", textContent: name }));
      if (meta) li.append(Object.assign(document.createElement("span"), { className: "meta", textContent: meta }));
      li.onclick = go;
      return li;
    };
    const rows = [];
    if (path !== MUSIC) rows.push(row(I.up, path.split("/").slice(0, -1).pop(), "", () => this.browse(path.slice(0, path.lastIndexOf("/")))));
    for (const i of got) {
      if (FOLDERISH.has(i.kind)) rows.push(row(I[i.kind] || I.folder, i.name, i.count ? String(i.count) : "", () => this.browse(i.path)));
      else if (AUDIO.has(i.kind)) rows.push(row(I[i.kind] || I.track, i.name, time(i.duration) || "", () => this.show(i, got)));
    }
    if (!got.some(i => FOLDERISH.has(i.kind) || AUDIO.has(i.kind)))
      rows.push(Object.assign(document.createElement("li"), { className: "empty", textContent: "Nothing to play here." }));
    list.classList.add("walking");
    list.replaceChildren(...rows);
  }
  play(n) {
    if (!this.queue || n < 0 || n >= this.queue.length) return;
    this.at = n;
    const t = this.queue[n];
    // the same sound again (asked for twice): from its start, without loading it anew (the browser stalled on that,
    // Gab, 23 Nov: "I asked to play a given track, and it seemed like it crashed")
    const src = raw(t.audio || t.path);
    if (this.audio.getAttribute("src") === src && !this.audio.error) this.audio.currentTime = 0;
    else this.audio.src = src;
    this.audio.play().catch(() => {});
    this.querySelector(".pl-now b").textContent = t.name;
    this.querySelector(".pl-now small").textContent = t.path.split("/").slice(0, -1).join(" / ") || "Home";
    const art = this.querySelector(".pl-art");
    // the playing track's own cover (its album's, from the board), else the folder's: a queue of the whole library
    // (TermNL's "play some music") wore the first album's cover on every track (Gab, 24 Nov: "the cover of the track
    // which is playing is not the right one when I'm moving to other tracks")
    const cover = t.cover || this.cover;
    art.innerHTML = cover ? `<img alt="" src="${raw(cover)}">` : I[t.kind] || I.track;
    [...this.querySelectorAll(".pl-queue li")].forEach((li, i) => li.classList.toggle("here", i === n));
    this.querySelector(".readm").hidden = t.kind !== "memo";  // a memo playing: its text, in the Reader
    retitle(this, t.name);
    this.tell();
  }
}

export default {
  id: "player",
  name: "Player",
  said: ["music", "music player"],
  icon: glyph(`<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>`),
  size: [380, 520],
  launcher: true,
  dock: true,
  opens: ["track", "episode", "memo"],
  element: AppPlayer,
};
