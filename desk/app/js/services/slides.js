// The slide on show. The server keeps it (one for the whole desk), so the board's own screen, a
// laptop on the cable and the phone all follow the same one. This page asks for it and waits for
// the next change (/api/slides/now holds the answer until then), and tells the bus each time:
// main.js opens the Slides app when a deck starts, the app draws the slide.
import { bus } from "./device.js";

export let now = { seq: -1, deck: null, i: 0, n: 0, black: false, full: false };

// one line of the slides' words: "open <deck>", "next", "prev", "go <n>", "black", "full", "end"
export async function steer(words) {
  const r = await fetch("/api/slides", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ do: words }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "the device answered " + r.status);
  return data;
}
// the decks, and those whose slides are still being made (they can't be opened until they are)
export const decks = () => fetch("/api/slides").then(r => r.json()).then(d => ({ names: d.decks, preparing: d.preparing || [] }));
export const deck = name => fetch("/api/slides/deck?name=" + encodeURIComponent(name)).then(r => r.json());

(async function follow() {
  for (;;) {
    try {
      const r = await fetch("/api/slides/now?after=" + now.seq);
      if (!r.ok) throw new Error();
      const got = await r.json();
      if (got.seq !== now.seq) { now = got; bus.dispatchEvent(new CustomEvent("slide", { detail: now })); }
    } catch { await new Promise(ok => setTimeout(ok, 3000)); } // the server is away: ask again a little later
  }
})();
