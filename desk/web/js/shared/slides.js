// The slide on show. The server keeps it (one for the whole desk), so the board's own screen, a laptop on the cable
// and the phone all follow the same one. This page asks for it and waits for the next change (/api/slides/now holds
// the answer until then), and says so each time: main.js opens Slides when a deck starts, the app draws the slide.
// The old page's services/slides.js, carried over as it was (Gab, 24 Nov: "we forgot to port the slide app").

export const slides = new EventTarget();
export let now = { seq: -1, deck: null, i: 0, n: 0, black: false, full: false };

// one line of the slides' words: "open <deck>", "next", "prev", "go <n>", "black", "full", "end"
export async function steer(words) {
  const r = await fetch("/api/slides", { method: "POST", headers: { "X-Desk": "1", "Content-Type": "application/json" }, body: JSON.stringify({ do: words }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "the desk answered " + r.status);
  return data;
}
// the decks, and those whose slides are still being made (they can't be opened until they are)
export async function decks() {
  const r = await fetch("/api/slides"), d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "the desk answered " + r.status);
  return { names: d.decks, preparing: d.preparing || [] };
}
// a deck: its title, its count, and the folder of its pictures (Slides/<deck>/.deck/)
export async function deck(name) {
  const r = await fetch("/api/slides/deck?name=" + encodeURIComponent(name)), d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || "the desk answered " + r.status);
  return d;
}
// a slide's picture: the deck's folder is hidden (.deck), which /api/raw refuses; /api/fs/raw serves it, as before
export const picture = (d, i) => "/api/fs/raw?path=" + encodeURIComponent(d.path + String(i).padStart(2, "0") + ".jpg");

(async function follow() {
  for (;;) {
    try {
      const r = await fetch("/api/slides/now?after=" + now.seq);
      if (!r.ok) throw new Error();
      const got = await r.json();
      if (got.seq !== now.seq) { now = got; slides.dispatchEvent(new CustomEvent("slide", { detail: now })); }
    } catch { await new Promise(ok => setTimeout(ok, 3000)); }  // the board is away, or the desk locked: ask again a little later
  }
})();
