// The Terminal: a real bash near the board (its screen, its cable), and the log of every command of this session
// (Gab, 23 Nov: "see how terminal will cope with it"). The shell is drawn by xterm (js/lib/xterm).
import { glyph } from "../../../shared/icons.js";
import { el } from "../../../utils/dom.js";
import { api, run, history, bus, commandLine } from "./commands.js";

// ---- the Terminal ----
let xterm;
const script = src => new Promise((ok, no) => document.head.append(Object.assign(document.createElement("script"), { src, onload: ok, onerror: no })));
const loadXterm = () => xterm ||= (async () => {
  document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: "js/lib/xterm/xterm.css" }));
  await script("js/lib/xterm/xterm.js");
  await script("js/lib/xterm/xterm-addon-fit.js");
})();
// 1-bit, as on the desk: every ANSI colour is the theme's ink on the theme's paper
function colours() {
  const cs = getComputedStyle(document.documentElement);
  const bg = cs.getPropertyValue("--bg").trim() || "#000", fg = cs.getPropertyValue("--fg").trim() || "#eee";
  const all = Object.fromEntries(["red", "green", "yellow", "blue", "magenta", "cyan", "white"].flatMap(c => [[c, fg], ["bright" + c[0].toUpperCase() + c.slice(1), fg]]));
  return { ...all, background: bg, foreground: fg, cursor: fg, cursorAccent: bg, selectionBackground: fg, selectionForeground: bg, black: bg, brightBlack: fg };
}

class AppTerminal extends HTMLElement {
  connectedCallback() {
    if (this.log) return;
    this.innerHTML = `<div class="tn-tabs" hidden><button class="chip" data-view="shell">Shell</button><button class="chip" data-view="log">Commands</button></div>
      <div class="tn-shell" hidden></div>
      <div class="tn-log"><div class="tn-lines"><p class="muted read">A real shell opens here only on the board’s own screen or over its cable. This is the log: the commands the skills hand to the board show up here. You can type one too: only the forms a skill declares are run (try “df -h /” or “free -h”).</p></div>
      <form class="tn-entry"><input class="field num" name="c" placeholder="$" autocomplete="off" spellcheck="false" aria-label="Command"><button class="btn">Run</button></form></div>`;
    this.log = this.querySelector(".tn-log");
    this.lines = this.querySelector(".tn-lines");
    history.forEach(h => this.line(h));
    this.onCommand = e => this.line(e.detail);
    bus.addEventListener("command", this.onCommand);
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const c = e.target.c;
      if (c.value.trim()) run(c.value.trim());
      c.value = "";
    });
    api("/api/info").then(a => { if (a.shell && this.isConnected) this.shell(); }).catch(() => {});
  }
  closing() {
    bus.removeEventListener("command", this.onCommand);
    this.leave?.();
  }
  line(r) {
    const block = el("div", "tn-block");
    block.append(commandLine(r));
    if (r.out || r.why) block.append(el("pre", "tn-out", r.out || r.why));
    this.lines.append(block);
    this.lines.scrollTop = this.lines.scrollHeight;
  }
  async shell() {
    const tabs = this.querySelector(".tn-tabs"), box = this.querySelector(".tn-shell");
    tabs.hidden = false;
    this.lines.firstElementChild.textContent = "The commands the skills hand to the board show up here. You can type one too: only the forms a skill declares are run (try “df -h /” or “free -h”).";
    await loadXterm();
    if (!this.isConnected) return;
    const cs = getComputedStyle(document.documentElement);
    const term = new window.Terminal({ fontFamily: cs.getPropertyValue("--font-ui").trim() || "monospace", fontSize: 13, cursorBlink: true, theme: colours() });
    const fit = new window.FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(box);
    const ws = new WebSocket(location.origin.replace(/^http/, "ws") + "/api/shell");
    ws.binaryType = "arraybuffer";
    const send = m => { if (ws.readyState === 1) ws.send(JSON.stringify(m)); };
    const size = () => {
      if (!box.offsetWidth) return;
      fit.fit();
      send({ rows: term.rows, cols: term.cols });
    };
    ws.onopen = size;
    ws.onmessage = e => term.write(new Uint8Array(e.data));
    ws.onclose = () => term.write("\r\n[the shell has closed: close this window and open the Terminal again for a new one]\r\n");
    term.onData(keys => send({ in: keys }));
    const watch = new ResizeObserver(size);
    watch.observe(box);
    const onTheme = () => { term.options.theme = colours(); };
    const themeWatch = new MutationObserver(onTheme);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "class", "style"] });
    const view = name => {
      box.hidden = name !== "shell";
      this.log.hidden = name === "shell";
      for (const b of tabs.children) b.classList.toggle("here", b.dataset.view === name);
      if (name === "shell") { size(); term.focus(); }
    };
    tabs.addEventListener("click", e => { if (e.target.dataset.view) view(e.target.dataset.view); });
    view("shell");
    this.leave = () => { themeWatch.disconnect(); watch.disconnect(); ws.close(); term.dispose(); };
  }
}

export default {
  id: "terminal",
  name: "Terminal",
  said: ["shell", "command line", "bash"],
  icon: glyph(`<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>`),
  size: [640, 400],
  launcher: true,
  element: AppTerminal,
};
