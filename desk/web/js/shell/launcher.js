// launcher.js — the full-screen overlay behind the left island's first button: the apps, as tiles, then the
// home's folders, as a compact list under their own heading, so the two read apart and the apps can grow
// (Gab, 23 Nov: "What it needs perhaps is a better split between apps and folders in this overlay"). Type
// to filter both, and to find files and folders anywhere in the home (the index, next/file_index.py: Gab, 23 Nov:
// "if I'm putting my click, which is part of the music tracks, it's not showing it"); a part with nothing hides. From SymbiOS v1 (core/launcher.js).
import { APPS, inLauncher } from "./loader.js";
import { launch } from "./wm.js";
import { items, raw, parent } from "../shared/api.js";
import { I } from "../shared/icons.js";
import { PLACE, appFor } from "../shared/kinds.js";

const launcher = document.getElementById("launcher"), grid = document.getElementById("launch-grid"), places = document.getElementById("launch-places"), search = document.getElementById("launch-search");
const appsPart = document.getElementById("launch-apps"), homePart = document.getElementById("launch-home"), none = document.getElementById("launch-none");
const filesPart = document.getElementById("launch-files"), found = document.getElementById("launch-found");
const FOLDERISH = new Set(["folder", "album", "artist", "show"]);
let asked = 0, timer = null, hits = [];
let folders = [];

function tile(glyph, name, act) {
  const b = document.createElement("button");
  b.className = "lapp";
  b.innerHTML = `<span class="glyph">${glyph}</span><span></span>`;
  b.lastChild.textContent = name;
  b.onclick = act;
  return b;
}
function build(f = "") {
  const hit = name => name.toLowerCase().includes(f.trim().toLowerCase());
  grid.replaceChildren(...Object.entries(APPS).filter(([id, a]) => inLauncher(id) && hit(a.name))
    .map(([id, a]) => tile(a.icon, a.name, () => launch(id, id === "files" ? { path: "", name: "Home", kind: "folder" } : undefined))));
  places.replaceChildren(...folders.filter(i => hit(i.name)).map(i => {
    const b = document.createElement("button");
    b.className = "row link";
    b.innerHTML = `<span class="g">${I[PLACE[i.name] || "folder"]}</span><span class="name"></span><span class="meta"></span>`;
    b.querySelector(".name").textContent = i.name;
    b.querySelector(".meta").textContent = i.count === 1 ? "1 item" : `${i.count} items`;
    b.dataset.path = i.path;
    b.onclick = () => launch("files", i);
    return b;
  }));
  appsPart.hidden = !grid.children.length;
  homePart.hidden = !places.children.length;
  // the files: from the index, asked a moment after the typing stops (the board walks no folder for it)
  clearTimeout(timer);
  if (f.trim().length < 2) { hits = []; paintFiles(); }
  else timer = setTimeout(() => findFiles(f.trim()), 200);
  shown();
}
const shown = () => { filesPart.hidden = !hits.length; none.hidden = !(appsPart.hidden && homePart.hidden && filesPart.hidden); };

async function findFiles(words) {
  const n = ++asked;
  let got = [];
  try { got = (await (await fetch("/api/search?q=" + encodeURIComponent(words))).json()).items || []; } catch { /* the desk is away */ }
  if (n !== asked) return;  // an older answer, the typing went on
  const top = new Set([...places.children].map(b => b.dataset.path));
  hits = got.filter(i => !top.has(i.path));  // the home's own folders are already listed above
  paintFiles();
}

function paintFiles() {
  found.replaceChildren(...hits.map(i => {
    const b = document.createElement("button");
    b.className = "row link";
    b.innerHTML = `<span class="g"></span><span class="name"></span><span class="meta"></span>`;
    b.querySelector(".g").innerHTML = i.cover ? `<img alt="" src="${raw(i.cover)}">` : I[i.kind] || I.file;
    b.querySelector(".name").textContent = i.name;
    b.querySelector(".meta").textContent = i.where;
    b.onclick = () => openFound(i);
    return b;
  }));
  shown();
}

// a folder opens in Files; a file in the app of its kind, among its folder's items (an album's other tracks)
async function openFound(item) {
  if (FOLDERISH.has(item.kind)) return launch("files", item);
  let among = [item];
  try { among = await items(parent(item.path)); } catch { /* alone, then */ }
  launch(appFor(item), item, among);
}

export async function openLauncher() {
  launcher.classList.add("open");
  search.value = "";
  build();
  setTimeout(() => search.focus(), 30);
  try { folders = (await items("")).filter(i => i.kind !== "file"); build(search.value); } catch { /* the desk is away */ }
}
export function closeLauncher() { launcher.classList.remove("open"); }

document.getElementById("launcher-btn").onclick = () => launcher.classList.contains("open") ? closeLauncher() : openLauncher();
search.oninput = e => build(e.target.value);
search.onkeydown = e => { if (e.key === "Enter") launcher.querySelector(".lapp, #launch-places .row, #launch-found .row")?.click(); };
launcher.onclick = e => { if (e.target === launcher || e.target.classList.contains("lpart")) closeLauncher(); };
