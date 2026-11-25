// Files: one folder of the home. Its items with their kinds (files.py); a tap selects, a double tap
// opens (a folder here, a file in the app of its kind). Drag items onto a folder (here, in another
// window, on the desktop) to move them; drop files from the computer into the window to put them here.
import { I, glyph } from "../../shared/icons.js";
import { items, call, raw, home, parent } from "../../shared/api.js";
import { line, PLACE, readMemo } from "../../shared/kinds.js";
import { retitle } from "../../shared/desk.js";
import { appPref, setAppPref, prefs } from "../../shared/prefs.js";
import { row, choice, section } from "../../shared/controls.js";
import { dropOn, isDeskDrag, moveDragged, DESK_TYPE, say } from "../../shared/drop.js";

// how a folder is shown, list or grid: the person's choice, kept on the board (Settings, or the view button);
// this screen's old choice until one is kept there
const oldView = () => { try { return localStorage.getItem("next.files.view"); } catch { return null; } };
const viewNow = () => appPref("files", "view", oldView() || "list");

const FOLDERISH = new Set(["folder", "album", "artist", "show"]);
const AUDIO = new Set(["track", "episode", "memo"]);
const coarse = matchMedia("(pointer: coarse)");

class AppFiles extends HTMLElement {
  connectedCallback() {
    if (this.bar) return;
    this.view = viewNow();
    this.onPrefs = e => { if (e.detail.key === "app.files" && viewNow() !== this.view) { this.view = viewNow(); this.render(); } };
    prefs.addEventListener("change", this.onPrefs);
    this.innerHTML = `<div class="fbar">
        <button class="ib up" title="Up (Backspace)">${I.up}</button>
        <div class="crumbs"></div>
        <button class="ib playall" title="Play all" hidden>${I.play}</button>
        <button class="ib readm" title="Read its text" hidden>${I.reader}</button>
        <button class="ib newf" title="New folder">${I.newfolder}</button>
        <button class="ib ren" title="Rename (F2)" disabled>${I.rename}</button>
        <button class="ib del" title="To the trash (Delete)" disabled>${I.trash}</button>
        <button class="ib viewb" title="List or grid"></button>
      </div><div class="fbody app-split"><nav class="app-side fside" aria-label="The home's folders"></nav><div class="fitems" tabindex="0"></div></div>`;
    this.bar = this.querySelector(".fbar");
    this.box = this.querySelector(".fitems");
    this.querySelector(".up").onclick = () => this.path && this.go(parent(this.path));
    this.querySelector(".newf").onclick = () => this.newFolder();
    this.querySelector(".ren").onclick = () => this.rename();
    this.querySelector(".del").onclick = () => this.trash();
    this.querySelector(".playall").onclick = () => this.playAll();
    this.querySelector(".readm").onclick = () => { const m = this.items.find(i => this.selected.has(i.path) && i.kind === "memo"); if (m) readMemo(m); };
    this.querySelector(".viewb").onclick = () => { this.view = this.view === "list" ? "grid" : "list"; setAppPref("files", "view", this.view).catch(() => {}); this.render(); };
    this.box.addEventListener("keydown", e => this.key(e));
    this.box.addEventListener("click", e => { if (e.target === this.box) this.select([]); });
    // drops into the window: things from the computer, or items of the desk, into this folder
    this.box.addEventListener("dragover", e => {
      if (!(e.dataTransfer.types.includes("Files") || isDeskDrag(e))) return;
      e.preventDefault(); e.stopPropagation();
      this.box.classList.add("over");
    });
    this.box.addEventListener("dragleave", e => { if (!this.box.contains(e.relatedTarget)) this.box.classList.remove("over"); });
    this.box.addEventListener("drop", e => {
      e.preventDefault(); e.stopPropagation();
      this.box.classList.remove("over");
      if (isDeskDrag(e)) moveDragged(e, this.path);
      else dropOn(e.dataTransfer, this.path);
    });
    this.side = this.querySelector(".fside");
    this.onChanged = () => { this.load(); this.places(); };
    home.addEventListener("changed", this.onChanged);
    this.places();
  }
  closing() { home.removeEventListener("changed", this.onChanged); prefs.removeEventListener("change", this.onPrefs); }

  show(item) { this.go(item?.path || ""); }
  async go(path) {
    this.path = path;
    this.selected = new Set();
    retitle(this, path ? path.split("/").pop() : "Home", path);
    const crumbs = this.querySelector(".crumbs");
    const parts = path ? path.split("/") : [];
    crumbs.replaceChildren(...["Home", ...parts].map((name, i) => {
      const b = document.createElement("button");
      b.textContent = name;
      b.onclick = () => this.go(parts.slice(0, i).join("/"));
      return b;
    }));
    this.mark();
    await this.load();
    this.box.focus({ preventScroll: true });
  }
  async load() {
    try { this.items = await items(this.path); }
    catch (e) { this.items = []; if (String(e.message).startsWith("nothing at")) return this.go(parent(this.path)); say(e.message); }
    this.selected = new Set([...this.selected].filter(p => this.items.some(i => i.path === p)));
    this.render();
  }
  // the sidebar: Home and the home's own folders, as v1's Files had them (Gab, 23 Nov: "we don't have a
  // sidebar to display the defined folders like music, pictures, documents"). Each takes drops too.
  async places() {
    let top = [];
    try { top = (await items("")).filter(i => i.kind !== "file"); } catch { /* the desk is away */ }
    this.side.replaceChildren(...[{ path: "", name: "Home" }, ...top].map(item => {
      const b = document.createElement("button");
      b.className = "row link";
      b.dataset.path = item.path;
      b.innerHTML = `<span class="g">${I[PLACE[item.name] || (item.path ? "folder" : "home")]}</span><span class="name"></span>`;
      b.querySelector(".name").textContent = item.name;
      b.onclick = () => this.go(item.path);
      b.addEventListener("dragover", e => { if (isDeskDrag(e) || e.dataTransfer.types.includes("Files")) { e.preventDefault(); e.stopPropagation(); b.classList.add("over"); } });
      b.addEventListener("dragleave", () => b.classList.remove("over"));
      b.addEventListener("drop", e => {
        e.preventDefault(); e.stopPropagation(); b.classList.remove("over");
        if (isDeskDrag(e)) moveDragged(e, item.path); else dropOn(e.dataTransfer, item.path);
      });
      return b;
    }));
    this.mark();
  }
  mark() {
    const top = (this.path || "").split("/")[0];
    for (const b of this.side?.children || []) b.classList.toggle("here", b.dataset.path === top);
  }
  render() {
    this.querySelector(".viewb").innerHTML = this.view === "list" ? I.grid : I.list;
    this.querySelector(".up").disabled = !this.path;
    this.querySelector(".playall").hidden = !this.items.some(i => AUDIO.has(i.kind));
    this.box.className = "fitems " + this.view;
    if (!this.items.length) {
      this.box.innerHTML = `<p class="empty">Empty. Drop files here.</p>`;
      return this.marks();
    }
    this.box.replaceChildren(...this.items.map(item => this.row(item)));
    this.marks();
  }
  row(item) {
    const r = document.createElement("div");
    r.className = "fitem";
    r.dataset.path = item.path;
    r.draggable = true;
    const pic = item.kind === "picture" ? item.path : item.cover;
    r.innerHTML = `<span class="ficon"></span><span class="fname"></span><span class="fline"></span>`;
    const icon = r.querySelector(".ficon");
    // a picture in the grid; in the list, only a cover (an album's, worn by its tracks), small
    if (pic && (this.view === "grid" || item.cover)) icon.innerHTML = `<img loading="lazy" decoding="async" alt="" src="${raw(pic)}">`;
    else icon.innerHTML = I[item.kind] || I.file;
    r.querySelector(".fname").textContent = item.name + (item.kind === "file" || item.kind === "document" || item.kind === "picture" || item.kind === "video" ? ext(item.path) : "");
    r.querySelector(".fline").textContent = line(item);
    r.addEventListener("click", e => {
      if (coarse.matches && !e.ctrlKey && !e.metaKey && !e.shiftKey) return this.open(item);
      this.pick(item, e);
    });
    r.addEventListener("dblclick", () => this.open(item));
    r.addEventListener("dragstart", e => {
      if (!this.selected.has(item.path)) this.select([item.path]);
      e.dataTransfer.setData(DESK_TYPE, JSON.stringify([...this.selected]));
      e.dataTransfer.setData("text/plain", [...this.selected].join("\n"));
      e.dataTransfer.effectAllowed = "move";
    });
    if (FOLDERISH.has(item.kind)) {
      r.addEventListener("dragover", e => {
        if (!(isDeskDrag(e) || e.dataTransfer.types.includes("Files"))) return;
        e.preventDefault(); e.stopPropagation();
        r.classList.add("over");
      });
      r.addEventListener("dragleave", () => r.classList.remove("over"));
      r.addEventListener("drop", e => {
        e.preventDefault(); e.stopPropagation();
        r.classList.remove("over");
        if (isDeskDrag(e)) moveDragged(e, item.path);
        else dropOn(e.dataTransfer, item.path);
      });
    }
    return r;
  }
  pick(item, e) {
    if (e.shiftKey && this.anchor) {
      const a = this.items.findIndex(i => i.path === this.anchor), b = this.items.indexOf(item);
      const [lo, hi] = a < b ? [a, b] : [b, a];
      return this.select(this.items.slice(lo, hi + 1).map(i => i.path), true);
    }
    this.anchor = item.path;
    if (e.ctrlKey || e.metaKey) {
      const s = new Set(this.selected);
      s.has(item.path) ? s.delete(item.path) : s.add(item.path);
      return this.select([...s]);
    }
    this.select([item.path]);
  }
  select(paths, keepAnchor) {
    this.selected = new Set(paths);
    if (!keepAnchor && paths.length === 1) this.anchor = paths[0];
    this.marks();
  }
  marks() {
    for (const r of this.box.querySelectorAll(".fitem")) r.classList.toggle("sel", this.selected.has(r.dataset.path));
    this.querySelector(".ren").disabled = this.selected.size !== 1;
    this.querySelector(".del").disabled = !this.selected.size;
    const memo = this.selected.size === 1 && this.items.find(i => this.selected.has(i.path))?.kind === "memo";
    this.querySelector(".readm").hidden = !memo;  // a memo chosen: its text, in the Reader
  }
  open(item) {
    if (FOLDERISH.has(item.kind)) return this.go(item.path);
    document.dispatchEvent(new CustomEvent("desk:open", { detail: { item, among: this.items } }));
  }
  playAll() {
    const first = this.items.find(i => AUDIO.has(i.kind));
    if (first) document.dispatchEvent(new CustomEvent("desk:open", { detail: { item: first, among: this.items } }));
  }
  key(e) {
    if (e.target.closest("input")) return;
    const i = this.items.findIndex(x => this.selected.has(x.path));
    const cols = this.view === "grid" ? Math.max(1, Math.floor(this.box.clientWidth / (this.box.querySelector(".fitem")?.offsetWidth || 1))) : 1;
    const moveTo = n => { const it = this.items[Math.max(0, Math.min(this.items.length - 1, n))]; if (it) { this.select([it.path]); this.box.querySelector(`[data-path="${CSS.escape(it.path)}"]`)?.scrollIntoView({ block: "nearest" }); } };
    if (e.key === "ArrowDown") { e.preventDefault(); moveTo(i < 0 ? 0 : i + cols); }
    else if (e.key === "ArrowUp") { e.preventDefault(); moveTo(i < 0 ? 0 : i - cols); }
    else if (e.key === "ArrowRight" && cols > 1) { e.preventDefault(); moveTo(i + 1); }
    else if (e.key === "ArrowLeft" && cols > 1) { e.preventDefault(); moveTo(i - 1); }
    else if (e.key === "Enter" && i >= 0) this.open(this.items[i]);
    else if (e.key === "Backspace" && this.path) { e.preventDefault(); this.go(parent(this.path)); }
    else if (e.key === "Delete") this.trash();
    else if (e.key === "F2") { e.preventDefault(); this.rename(); }
    else if ((e.ctrlKey || e.metaKey) && e.key === "a") { e.preventDefault(); this.select(this.items.map(x => x.path)); }
  }
  // a name typed in place: Enter keeps it, Escape or leaving lets it go
  ask(row, value, done) {
    const name = row.querySelector(".fname");
    const input = document.createElement("input");
    input.value = value;
    name.replaceChildren(input);
    input.focus();
    input.setSelectionRange(0, value.lastIndexOf(".") > 0 ? value.lastIndexOf(".") : value.length);
    let over = false;
    const end = keep => { if (over) return; over = true; keep && input.value.trim() && input.value.trim() !== value ? done(input.value.trim()) : this.render(); };
    input.addEventListener("keydown", e => { e.stopPropagation(); if (e.key === "Enter") end(true); if (e.key === "Escape") end(false); });
    input.addEventListener("blur", () => end(true));
    input.addEventListener("click", e => e.stopPropagation());
    input.addEventListener("dblclick", e => e.stopPropagation());
  }
  newFolder() {
    if (!this.items.length) this.box.replaceChildren();
    const row = this.row({ name: "", path: "", kind: "folder", count: 0 });
    row.draggable = false;
    this.box.prepend(row);
    this.ask(row, "New folder", async name => {
      try { const d = await call("folder", { path: (this.path ? this.path + "/" : "") + name }); this.selected = new Set([d.path]); }
      catch (e) { say(e.message); this.render(); }
    });
  }
  rename() {
    const [path] = this.selected;
    const row = path && this.box.querySelector(`[data-path="${CSS.escape(path)}"]`);
    if (!row || this.selected.size !== 1) return;
    row.draggable = false;
    this.ask(row, path.split("/").pop(), async name => {
      try { const d = await call("rename", { path, name }); this.selected = new Set([d.path]); }
      catch (e) { say(e.message); this.render(); }
    });
  }
  async trash() {
    if (!this.selected.size) return;
    const paths = [...this.selected];
    try { await call("trash", { paths }); say(paths.length === 1 ? `${paths[0].split("/").pop()} is in the trash.` : `${paths.length} items are in the trash.`); }
    catch (e) { say(e.message); }
  }
}
const ext = path => { const m = path.match(/(\.[^./]+)$/); return m ? m[1] : ""; };

export default {
  id: "files",
  name: "Files",
  said: ["file system", "file manager"],
  icon: glyph(`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`),
  size: [680, 460],
  launcher: true,
  dock: true,
  many: true,
  opens: ["folder", "album", "artist", "show"],
  element: AppFiles,
  settings: () => [section("Folders", [row("Shown as", "The view button in Files changes it too",
    choice([["list", "List"], ["grid", "Grid"]], viewNow(), view => setAppPref("files", "view", view)))])],
};
