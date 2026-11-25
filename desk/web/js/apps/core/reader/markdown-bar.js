// markdown-bar.js — buttons over a Markdown text being written: heading, bold, italic, link, list, quote, table (Gab,
// 23 Nov: "a kind of markdown file editor with like bold, headline, list ... with buttons a bit like Apostrophe";
// "something extremely simple"). Carried from brainboard's doc editor (app/js/components/docEditor.js: wrapSel,
// prefixLine, insertBlock), its glyphs drawn in the desk's line style. Each button changes the text as typing would
// (an "input" event), so the app holding it sees the change (the Reader: "not saved"). Ctrl+B, Ctrl+I, Ctrl+K too.
const svg = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
const G = {
  heading: svg(`<path d="M6 4v16M18 4v16M6 12h12"/>`),
  bold: svg(`<path d="M7 4h6a4 4 0 0 1 0 8H7zM7 12h7a4 4 0 0 1 0 8H7z"/>`),
  italic: svg(`<path d="M19 4h-9M14 20H5M15 4 9 20"/>`),
  link: svg(`<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>`),
  list: svg(`<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>`),
  quote: svg(`<path d="M5 6h5v6H7.5L6 17M14 6h5v6h-2.5L15 17"/>`),
  table: svg(`<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18M9 4v16"/>`),
};
const TABLE = "| Column | Column |\n| --- | --- |\n|  |  |\n";

export function markdownBar(ta) {
  // the text changed as typing would change it, the selection put back where it belongs
  const apply = (value, s, e) => {
    ta.value = value;
    ta.focus();
    ta.setSelectionRange(s, e ?? s);
    ta.dispatchEvent(new Event("input", { bubbles: true }));
  };
  const wrap = (before, after, placeholder) => {
    const s = ta.selectionStart, e = ta.selectionEnd, v = ta.value, sel = v.slice(s, e) || placeholder;
    apply(v.slice(0, s) + before + sel + after + v.slice(e), s + before.length, s + before.length + sel.length);
  };
  // the line the cursor is on, or every line selected, starts with the mark; pressed again, the mark comes off
  const lines = mark => {
    const v = ta.value, s = ta.selectionStart, e = ta.selectionEnd;
    const last = e > s && v[e - 1] === "\n" ? e - 1 : e;  // a selection ending at a line's start stops before it
    const from = v.lastIndexOf("\n", s - 1) + 1, to = v.indexOf("\n", last), end = to === -1 ? v.length : to;
    const block = v.slice(from, end).split("\n"), off = block.every(l => l.startsWith(mark));
    const out = block.map(l => off ? l.slice(mark.length) : l.startsWith(mark) ? l : mark + l).join("\n");
    apply(v.slice(0, from) + out + v.slice(end), from, from + out.length);
  };
  // a block of its own (a table): after the line the cursor is on, never cutting it in two
  const block = text => {
    const v = ta.value, nl = v.indexOf("\n", ta.selectionEnd), at = nl === -1 ? v.length : nl + 1;
    const chunk = (at > 0 && v[at - 1] !== "\n" ? "\n" : "") + text + (at < v.length && v[at] !== "\n" ? "\n" : "");
    apply(v.slice(0, at) + chunk + v.slice(at), at + chunk.length);
  };
  const actions = {
    heading: ["Heading", () => lines("## ")],
    bold: ["Bold (Ctrl+B)", () => wrap("**", "**", "bold")],
    italic: ["Italic (Ctrl+I)", () => wrap("*", "*", "italic")],
    link: ["Link (Ctrl+K)", () => wrap("[", "](https://)", "words")],
    list: ["List", () => lines("- ")],
    quote: ["Quote", () => lines("> ")],
    table: ["Table", () => block(TABLE)],
  };
  const bar = document.createElement("div");
  bar.className = "md-bar";
  for (const [name, [title, act]] of Object.entries(actions)) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ib";
    b.title = b.ariaLabel = title;
    b.innerHTML = G[name];
    b.addEventListener("mousedown", e => e.preventDefault()); // the text keeps its selection
    b.addEventListener("click", act);
    bar.append(b);
    if (name === "link") bar.append(Object.assign(document.createElement("span"), { className: "md-sep" }));
  }
  ta.addEventListener("keydown", e => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.shiftKey) return;
    const act = { b: actions.bold, i: actions.italic, k: actions.link }[e.key.toLowerCase()];
    if (act) { e.preventDefault(); act[1](); }
  });
  return bar;
}
