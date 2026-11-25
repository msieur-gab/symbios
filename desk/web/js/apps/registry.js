// The registry of the desk's apps, in the launcher's order. Adding an app = its file, and one line here; the shell's
// loader (shell/loader.js) loads them, and the add-ons the board announces.
// Each file ends with what the desk needs to know of it (export default):
//   id        its name in the code; its element is <app-ID>
//   name      what the person reads (launcher, dock, window)
//   icon      its glyph: glyph(drawing) for its own, I.something when the shell draws it too
//   size      its window when it opens: [width, height]
//   launcher  a tile in the launcher (else it opens from a file)
//   said      what else people call it, for TermNL ("open music" opens the Player): its name is always one
//   dock      kept on the dock (a running app shows there anyway)
//   many      several windows of it at once (Files on two folders, two pictures)
//   opens     the kinds of file it opens (the table of kinds sends them here); "text": a plain file that reads as text,
//             "file": any other file
//   element   the element drawing it (a class extending HTMLElement); given a file through its show(item, among)
//   settings  its block in Settings, if any: a function answering its rows (shared/controls.js), which keep its own
//             preferences (appPref, setAppPref: shared/prefs.js)
// The core apps (apps/core/) are the ones the desk can't do without; the others are beside this file.
import files from "./core/files.js";
import player from "./core/player.js";
import reader from "./core/reader/reader.js";
import picture from "./core/picture.js";
import video from "./core/video.js";
import doc from "./core/document.js";
import termnl from "./core/termnl/termnl.js";
import terminal from "./core/termnl/terminal.js";
import memos from "./memos.js";
import activity from "./activity.js";
import slides from "./slides.js";
import monitor from "./core/monitor.js";
import settings from "./core/settings.js";
import mesh from "./core/mesh/mesh.js";
import info from "./core/info.js";

export default [files, player, reader, picture, video, doc, termnl, terminal, memos, slides, activity, monitor, settings, mesh, info];
