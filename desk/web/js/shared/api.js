// What the page asks of the home (server.py). Paths are relative to the home, "/"-separated.
export const raw = path => "/api/raw?path=" + encodeURIComponent(path);

export async function items(path = "") {
  const r = await fetch("/api/items?path=" + encodeURIComponent(path));
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || r.status);
  return d.items;
}

export async function call(route, body) {
  const r = await fetch("/api/" + route, { method: "POST", headers: { "X-Desk": "1", "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.status);
  changed();
  return d;
}

export async function text(path) {
  const r = await fetch(raw(path));
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.status);
  return r.text();
}

// one event when the home changed, so every open folder looks again
export const home = new EventTarget();
export const changed = () => home.dispatchEvent(new Event("changed"));

export const parent = path => path.includes("/") ? path.slice(0, path.lastIndexOf("/")) : "";
export const base = path => path.slice(path.lastIndexOf("/") + 1);
