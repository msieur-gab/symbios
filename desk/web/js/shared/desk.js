// What an app may ask of the desk around it: open a file in the app of its kind, start an app, name its window,
// the dock hiding itself. The apps' only door to the shell: an app never imports shell/, so an app can't break the
// shell, nor another app. The shell plugs its own functions in once, at the start (main.js: connect).
let shell = null;
export function connect(functions) { shell = functions; }

// a file or folder, in the app of its kind (the table of kinds); among: the others beside it (a queue, a folder)
export const open = (item, among) => document.dispatchEvent(new CustomEvent("desk:open", { detail: { item, among } }));
// an app by its id, given a file or nothing; the window it opened in (or brought forward)
export const start = (app, item, among) => shell.launch(app, item, among);
// the window holding this element is named after what it shows; key: what tells two such windows apart
// (only an app that is the window's own: the Reader inside Memos leaves Memos' title alone)
export const retitle = (inside, title, key) => inside.parentElement?.classList.contains("win-body") && shell.retitle(inside, title, key);
// the window named after the file it shows
export const titled = (inside, item) => retitle(inside, item.name || item.path.split("/").pop(), item.path);
// the window holding this element over the whole screen, above the dock, or back in its place
export const fullScreen = (inside, on) => shell.fullScreen(inside, on);
// the dock slides away, and comes back at the bottom edge
export const dockHides = () => shell.dockAutoEnabled();
export const setDockHides = on => shell.setDockAuto(on);
// every app the desk has (the registry's and the add-ons'), as each describes itself: for Settings
export const apps = () => shell.apps();
// the apps that have a window open, by id; and every window of one closed (TermNL's "close slides")
export const running = () => shell.running();
export const close = app => shell.close(app);
