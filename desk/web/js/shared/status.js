// The board's state, as the desk reads it (/api/status): load, memory, temperature, disk, uptime. The Monitor and
// the quick panel's foot both show it.
export async function status() {
  const r = await fetch("/api/status");
  if (!r.ok) throw new Error(r.status);
  return r.json();
}
export const uptime = s => { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return (h >= 24 ? Math.floor(h / 24) + "d " : "") + (h % 24) + "h " + m + "m"; };
