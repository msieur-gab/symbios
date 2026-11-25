// The table of kinds, on the page's side: for each kind files.py gives an item, its glyph, the line
// under its name, and the app that opens it (Gab, 17 Oct: "opening files by types inside the matching
// app is the best scenario"). A folder of any kind opens in Files, wherever it lives.
import { size, time, day } from "../utils/format.js";

// each of the home's own folders wears the glyph of what it holds (Files' sidebar, the launcher)
export const PLACE = { Music: "track", Pictures: "picture", Videos: "video", Documents: "document", Notes: "note", Memos: "memo", Downloads: "download", Inbox: "inbox", Articles: "article", Podcasts: "show" };

export const TEXT = /\.(md|markdown|txt|text|csv|tsv|json|log|ya?ml|toml|ini|conf|py|js|mjs|css|html?|sh|xml|srt|vtt)$/i;

// which app opens each kind: filled by the loader (shell/loader.js) from what each app says it opens (its `opens`); "text" is a
// plain file that reads as text, "file" any other
export const OPENS = {};

// a memo's text: its transcript.md, opened in the Reader with its Edit (Gab, 23 Oct: "a memo in the Editor"), from
// Files and from the Player; the memo itself still plays
export function readMemo(memo) {
  document.dispatchEvent(new CustomEvent("desk:open", { detail: { item: { path: memo.path + "/transcript.md", name: memo.name, kind: "note", bare: true } } }));
}

// the app for an item; a plain "file" opens in the Reader when it is text, else in Info
export function appFor(item) {
  if (item.kind === "file" && TEXT.test(item.path)) return OPENS.text || OPENS.file;
  return OPENS[item.kind] || OPENS.file;
}

// what is said under or beside a name, one short line per kind
export function line(item) {
  switch (item.kind) {
    case "folder": return item.count === 1 ? "1 item" : `${item.count} items`;
    case "album": return [item.artist, `${item.count} tracks`].filter(Boolean).join(" · ");
    case "artist": return item.count === 1 ? "1 album" : `${item.count} albums`;
    case "show": return `${item.count} episodes`;
    case "track": return [item.number && "#" + item.number, time(item.duration) || size(item.size)].filter(Boolean).join(" · ");  // the length, from the tags the index keeps
    case "episode": return [item.date, time(item.duration)].filter(Boolean).join(" · ");
    case "memo": return [item.date, time(item.duration)].filter(Boolean).join(" · ");
    default: return [item.kind === "file" ? (item.path.match(/\.([^./]+)$/)?.[1] || "file").toLowerCase() : item.kind, size(item.size), day(item.modified)].filter(Boolean).join(" · ");
  }
}
