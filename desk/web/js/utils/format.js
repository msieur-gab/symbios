// How sizes, lengths and dates are written, that know nothing of the desk.

// a file's size: "812 B", "4.2 MB"
export function size(n) {
  if (n == null) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + " " + u[i];
}
// a length in seconds: "3:07", "1:02:45"
export function time(s) {
  if (!s || !Number.isFinite(s)) return "";  // an unknown length (Infinity, NaN) says nothing
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor(s / 60) % 60, sec = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
// a day, from milliseconds: "24 Nov 2026"
export const day = ms => ms ? new Date(ms).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" }) : "";
