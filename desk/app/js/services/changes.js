// What happens on the desk, as it happens (signals.py): files placed by the inbox, memos and decks made,
// and the heavy work under way. This page asks for what came after the last thing it heard and waits for
// the answer (/api/changes holds it until something happens), then tells the bus: "files" with the
// folders that changed (none: reload everything shown, after a missed stretch or a restarted desk), so each
// open app updates its own list, never what plays or shows; and "tasks", for Activity.
import { bus } from "./device.js";

export let tasks = [];
export let skew = 0; // this screen's clock minus the board's, for the time left of a task

(async function follow() {
  let seq = -1, boot = 0;
  for (;;) {
    try {
      const r = await fetch(`/api/changes?after=${seq}&boot=${boot}`);
      if (!r.ok) throw new Error();
      const d = await r.json();
      skew = Date.now() / 1000 - d.now;
      tasks = d.tasks;
      bus.dispatchEvent(new CustomEvent("tasks", { detail: tasks }));
      // the first answer only says where things stand: the open apps loaded their lists themselves
      if (seq !== -1 && (d.missed || d.changes.length))
        bus.dispatchEvent(new CustomEvent("files", { detail: { folders: d.missed ? null : d.changes.map(c => c.folder) } }));
      seq = d.seq; boot = d.boot;
    } catch { await new Promise(ok => setTimeout(ok, 3000)); } // the board is away: ask again a little later
  }
})();

// whether a "files" signal is about a folder (or everything): Music, Slides… listen only to their own
export const about = (e, folder) => !e.detail?.folders || e.detail.folders.some(f => f === folder || f.startsWith(folder + "/"));
