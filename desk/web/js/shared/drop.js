// Things dropped from the computer: files, whole folders (their paths kept, so an album stays an album),
// zips. Sent one file at a time, so nothing big waits in the board's memory, with a panel that says how
// far it is and can stop it. Then the drop is placed: into the folder it was dropped on, or, dropped on
// the desktop, where the rulebook says (Inbox/rules.md). From Gab's drop-anywhere prototype (~/dev/file-system).
import { call, changed } from "./api.js";
import { size } from "../utils/format.js";

export const DESK_TYPE = "application/x-desk-paths";
export const isDeskDrag = e => e.dataTransfer.types.includes(DESK_TYPE);
export async function moveDragged(e, into) {
  const paths = JSON.parse(e.dataTransfer.getData(DESK_TYPE) || "[]");
  if (!paths.length) return;
  try { await call("move", { paths, into }); } catch (err) { say(err.message); }
}

// the files of a drop, each with its path as dropped ("Album/01.mp3"); entries must be taken before any await
function collect(dt) {
  const entries = [...(dt.items || [])].filter(i => i.kind === "file").map(i => i.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) return Promise.resolve([...dt.files].map(file => ({ file, path: file.name })));
  const out = [];
  const walk = (entry, prefix) => new Promise(resolve => {
    if (entry.name.startsWith(".")) return resolve();
    if (entry.isFile) return entry.file(file => { out.push({ file, path: prefix + file.name }); resolve(); }, () => resolve());
    const reader = entry.createReader(), all = [];
    const more = () => reader.readEntries(async batch => {  // at most 100 at a time: ask until it answers none
      if (batch.length) { all.push(...batch); return more(); }
      for (const child of all) await walk(child, prefix + entry.name + "/");
      resolve();
    }, () => resolve());
    more();
  });
  return Promise.all(entries.map(e => walk(e, ""))).then(() => out);
}

const panel = document.getElementById("drop-panel");
let busy = false;

export async function dropOn(dt, into) {
  const listing = collect(dt);
  if (busy) return say("One drop at a time: wait for this one to finish.");
  busy = true;
  const list = await listing;
  if (!list.length) { busy = false; return; }
  const batch = Math.random().toString(36).slice(2, 12) + Date.now().toString(36);
  const total = list.reduce((n, f) => n + f.file.size, 0);
  let sent = 0, stopped = false, xhr = null;
  panel.hidden = false;
  // every line one line high, whatever its text, so the panel never jumps (Gab, 23 Nov: "jumping up and down
  // because the lines were sometimes one line or two lines"): the file's name ends with "…", the numbers keep their width
  panel.innerHTML = `<div class="dp-head"><b></b><button class="btn dp-stop">Stop</button></div>
    <div class="bar"><i></i></div>
    <div class="dp-now"><span class="dp-count num"></span><span class="dp-name"></span></div>
    <div class="dp-rate num muted"></div><div class="dp-line"></div>`;
  const head = panel.querySelector("b"), bar = panel.querySelector(".bar i"), line = panel.querySelector(".dp-line");
  const count = panel.querySelector(".dp-count"), nameEl = panel.querySelector(".dp-name"), rateEl = panel.querySelector(".dp-rate");
  const now = (n, path, text) => { count.textContent = `${n}/${list.length}`; nameEl.textContent = path; nameEl.title = path; rateEl.textContent = text; };
  head.textContent = `${list.length} file${list.length > 1 ? "s" : ""}, ${size(total)}` + (into ? ` → ${into || "Home"}` : "");
  panel.querySelector(".dp-stop").onclick = () => { stopped = true; xhr?.abort(); };
  const t0 = performance.now();
  try {
    for (const [n, { file, path }] of list.entries()) {
      if (stopped) break;
      now(n + 1, path, rateEl.textContent || "starting…");
      await new Promise((resolve, reject) => {
        xhr = new XMLHttpRequest();
        xhr.open("POST", `/api/drop?batch=${batch}&path=${encodeURIComponent(path)}&modified=${file.lastModified}`);
        xhr.setRequestHeader("X-Desk", "1");
        xhr.upload.onprogress = e => {
          const done = sent + e.loaded, secs = (performance.now() - t0) / 1000;
          bar.style.transform = `scaleX(${total ? done / total : 1})`;
          const rate = done / Math.max(secs, 0.1);
          now(n + 1, path, `${size(rate)}/s` + (rate ? ` · ${left((total - done) / rate)}` : ""));
        };
        xhr.onload = () => xhr.status === 200 ? resolve() : reject(new Error(JSON.parse(xhr.responseText || "{}").error || xhr.status));
        xhr.onerror = () => reject(new Error("the desk didn't answer"));
        xhr.onabort = () => reject(new Error("stopped"));
        xhr.send(file);
      });
      sent += file.size;
    }
  } catch (e) {
    stopped = true;
    line.textContent = path0(e.message);
  }
  if (stopped) {
    panel.querySelector(".dp-now")?.remove();
    rateEl.remove();
    head.textContent = "Stopped: nothing was placed.";
    await fetch(`/api/drop/cancel?batch=${batch}`, { method: "POST", headers: { "X-Desk": "1" } }).catch(() => {});
    return finish(4000);
  }
  bar.style.transform = "scaleX(1)";
  panel.querySelector(".dp-now").remove();
  rateEl.textContent = "placing…";
  try {
    const r = await fetch(`/api/drop/done?batch=${batch}` + (into != null ? `&into=${encodeURIComponent(into)}` : ""), { method: "POST", headers: { "X-Desk": "1" } });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || r.status);
    const again = d.placed.filter(p => p.already).length, placed = d.placed.length - again;
    rateEl.remove();
    head.textContent = [placed && `${placed} placed`, again && `${again} already on the desk`].filter(Boolean).join(", ") || "Nothing placed";
    line.replaceChildren(...d.placed.map(p => {
      const a = document.createElement("button");
      a.className = "btn quiet";
      // the same bytes already in the home are not stored twice: where they are, to open
      a.textContent = p.already ? `${p.name}: already in ${p.went || "Home"}` : `${p.name} → ${p.went}` + (p.left.length ? ` (${p.left.length} left out)` : "");
      a.title = p.left.join("\n");
      a.onclick = () => document.dispatchEvent(new CustomEvent("desk:open", { detail: { item: { path: p.went === "" ? "" : p.went, name: p.went || "Home", kind: "folder" } } }));
      return a;
    }));
    changed();
    finish(6000);
  } catch (e) {
    head.textContent = "Not placed: " + e.message;
    finish(6000);
  }
}
const left = s => s >= 90 ? `${Math.round(s / 60)} min left` : `${Math.max(1, Math.ceil(s))} s left`;
const path0 = m => m === "stopped" ? "Stopped." : "Stopped: " + m;

function finish(ms) {
  busy = false;
  panel.querySelector(".dp-stop")?.remove();  // nothing left to stop
  clearTimeout(panel.timer);
  panel.timer = setTimeout(() => { panel.hidden = true; }, ms);
}

const toast = document.getElementById("toast");
export function say(text) {
  toast.textContent = text;
  toast.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { toast.hidden = true; }, 4000);
}
