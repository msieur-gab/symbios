// What happens on the desk, as it happens (signals.py): files placed by the inbox, memos and decks made,
// and the heavy work under way. This page asks for what came after the last thing it heard and waits for
// the answer (/api/changes holds it until something happens), then says so: the open folders look again
// (api.js, changed), and "tasks" goes to Activity. The old page's services/changes.js, carried over as it was
// (the fold; Gab, 23 Nov: "Why the notification from the activity are not shown anymore").
import { changed } from "./api.js";

export const bus = new EventTarget();
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
      // ".lock": a screen asking the owner's phone, not a folder (lock.py): no folder needs to look again
      if (seq !== -1 && (d.missed || d.changes.some(c => !c.folder.startsWith(".")))) changed();
      seq = d.seq; boot = d.boot;
    } catch { await new Promise(ok => setTimeout(ok, 3000)); } // the board is away: ask again a little later
  }
})();
