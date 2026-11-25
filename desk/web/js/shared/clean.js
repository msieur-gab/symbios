// clean.js — HTML made from a file (a note's Markdown, an article) with nothing in it that can run on the desk. A page
// that runs on an allowed screen is the whole desk, and on the board's own screen the real shell too (symbios
// SECURITY.md, the review of 24 Nov, C2: a link written java&#9;script: passed the old check, as the browser drops the
// tab). So links are read the way the browser reads them (new URL) and only kept as http, https or mailto; what can
// carry script or a link of its own (svg, math, image maps, frames, forms) is taken out whole, and every on… attribute.
const GONE = "script, style, iframe, frame, frameset, object, embed, applet, form, input, button, textarea, select, " +
  "link, meta, base, svg, math, map, area, template, noscript, portal";
const LINKS = new Set(["href", "src", "xlink:href", "action", "formaction", "cite", "poster", "background", "data", "usemap", "longdesc"]);
const SAFE = new Set(["http:", "https:", "mailto:"]);

export function safeUrl(value) {
  try { return SAFE.has(new URL(value, location.href).protocol); } catch { return false; }
}

// html → a fragment to append; links open outside the desk, pictures load lazily and say nothing of where they are shown
export function clean(html) {
  const t = document.createElement("template");
  t.innerHTML = html;
  for (const e of t.content.querySelectorAll(GONE)) e.remove();
  for (const e of t.content.querySelectorAll("*")) {
    for (const a of [...e.attributes]) {
      const name = a.name.toLowerCase();
      if (name.startsWith("on") || name === "srcset" || name === "formtarget" || (LINKS.has(name) && !safeUrl(a.value))) e.removeAttribute(a.name);
    }
    if (e.tagName === "A") Object.assign(e, { target: "_blank", rel: "noopener noreferrer" });
    if (e.tagName === "IMG") Object.assign(e, { loading: "lazy", referrerPolicy: "no-referrer" });
  }
  return t.content;
}
