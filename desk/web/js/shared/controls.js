// The pieces Settings is made of, for the desk's own pages and for each app's (its description's settings): a section
// (a heading and its rows), a row (what it is, a word on it, its control), a switch, a choice among a few. Drawn in the design system's
// .set-row, .switch and .seg.
import { el } from "../utils/dom.js";

export function section(title, rows) {
  const s = el("section", "set-sec");
  if (title) s.append(el("h3", "eyebrow", title));
  s.append(...rows);
  return s;
}
export function row(label, hint, control) {
  const r = el("div", "set-row"), words = el("div");
  words.append(el("b", "", label));
  if (hint) words.append(el("small", "", hint));
  r.append(words, control);
  return r;
}
// on or off; set(on) may answer a promise: refused, the switch goes back and says why
export function toggle(label, on, set) {
  const b = el("button", "switch" + (on ? " on" : ""));
  b.setAttribute("aria-label", label);
  b.setAttribute("aria-pressed", on);
  b.onclick = () => {
    const now = !b.classList.contains("on");
    b.classList.toggle("on", now);
    b.setAttribute("aria-pressed", now);
    b.title = "";
    Promise.resolve(set(now)).catch(e => { b.classList.toggle("on", !now); b.setAttribute("aria-pressed", !now); b.title = "Not kept: " + e.message; });
  };
  return b;
}
// one of a few: options [[value, label]]; style(value) dresses a button (a typeface wears itself)
export function choice(options, current, set, style) {
  const seg = el("div", "seg");
  for (const [value, label] of options) {
    const b = el("button", value === current ? "on" : "", label);
    b.type = "button";
    if (style) style(b, value);
    b.onclick = () => {
      for (const o of seg.children) o.classList.toggle("on", o === b);
      Promise.resolve(set(value)).catch(() => {});
    };
    seg.append(b);
  }
  return seg;
}
