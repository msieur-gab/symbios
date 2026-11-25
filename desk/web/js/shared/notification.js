// notification.js — a small card at the top right, in the drop panel's styling: an app says that something has happened
// (Mesh, a new message). Its glyph and name with Open on the first line, who and where with the time on the second,
// the words on two lines at most (Gab, 24 Nov: "the icon on one line with the link to the app, and then below the
// person that sends ... and then the message"). One at a time: a newer one takes its place. It goes after a few seconds,
// not while the pointer is over it; a tap on it opens what it is about.
import { el } from "../utils/dom.js";

const STAY = 6000;
let card = null, timer = null;

function hide() { if (card) card.hidden = true; }
function later() { clearTimeout(timer); timer = setTimeout(hide, STAY); }

// notify({ icon, app, who, when, text, open }): icon an SVG, open() what a tap does
export function notify({ icon, app, who, when, text, open }) {
  if (!card) {
    card = el("div");
    card.id = "notification";
    card.setAttribute("role", "status");
    card.addEventListener("pointerenter", () => clearTimeout(timer));
    card.addEventListener("pointerleave", later);
    document.body.append(card);
  }
  const head = el("div", "nt-head"), glyph = el("span", "gl"), go = el("button", "btn", "Open ›");
  glyph.innerHTML = icon || "";
  go.type = "button";
  head.append(glyph, el("b", "", app), go);
  const line = el("div", "nt-who");
  line.append(el("span", "", who), el("span", "", when));
  card.replaceChildren(head, line, el("div", "nt-text", text));
  card.onclick = () => { hide(); open?.(); };
  // under the drop panel when both show: they share the top right
  const drop = document.getElementById("drop-panel");
  card.style.top = drop && !drop.hidden ? drop.getBoundingClientRect().bottom + 8 + "px" : "";
  card.hidden = false;
  later();
}
