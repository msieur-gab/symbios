// The terminal. Near the board (its own screen, or the USB cable) it is a real shell, as on
// symbios: bash on a pty, drawn by xterm.js. Everywhere it is also the log of every command of
// this session and what the device answered; what is typed in the log goes through the same
// check as what the skills send. Over WiFi the log is all there is.
import { bus, history, run, info } from "../services/device.js";
import { commandLine } from "./app-assistant.js";

let xterm; // xterm.js and its fit addon (window.Terminal, window.FitAddon), loaded with the first shell
const script = src => new Promise((ok, no) => document.head.append(Object.assign(document.createElement("script"), { src, onload: ok, onerror: no })));
const loadXterm = () => xterm ||= (async () => {
  document.head.append(Object.assign(document.createElement("link"), { rel: "stylesheet", href: "vendor/xterm.css" }));
  await script("vendor/xterm.js");
  await script("vendor/xterm-addon-fit.js");
})();

// 1-bit, as on symbios: every ANSI colour is the theme's ink on the theme's ground
function colours() {
  const cs = getComputedStyle(document.documentElement);
  const bg = cs.getPropertyValue("--bg").trim() || "#000000", fg = cs.getPropertyValue("--fg").trim() || "#e8e8e8";
  const all = Object.fromEntries(["red", "green", "yellow", "blue", "magenta", "cyan", "white"].flatMap(c => [[c, fg], ["bright" + c[0].toUpperCase() + c.slice(1), fg]]));
  return { ...all, background: bg, foreground: fg, cursor: fg, cursorAccent: bg, selectionBackground: fg, selectionForeground: bg, black: bg, brightBlack: fg };
}

class AppTerminal extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="log"><div class="pane"><div class="note">A real shell opens here only on the board’s own screen or over its USB cable. This is the log: commands the skills hand to the device show up here. You can type one too: only the forms a skill declares are run (try “df -h /” or “free -h”).</div></div>
      <form class="entry"><input name="c" placeholder="$" autocomplete="off" spellcheck="false" aria-label="Command"><button>Run</button></form></div>`;
    this.list = this.querySelector(".pane");
    history.forEach(h => this.show(h));
    this.onCommand = e => this.show(e.detail);
    bus.addEventListener("command", this.onCommand);
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const c = e.target.c;
      if (c.value.trim()) run(c.value.trim());
      c.value = "";
    });
    info().then(a => { if (a.shell && this.isConnected) this.shell(); }).catch(() => {});
  }
  disconnectedCallback() {
    bus.removeEventListener("command", this.onCommand);
    this.leave?.();
  }
  show(r) {
    const block = document.createElement("div");
    block.append(commandLine(r));
    if (r.out || r.why) block.append(Object.assign(document.createElement("pre"), { textContent: r.out || r.why }));
    this.list.append(block);
    this.list.scrollTop = this.list.scrollHeight;
  }
  // the real shell, in front of the log: two tabs, one bash for as long as the window is open
  async shell() {
    if (this.querySelector(".shell")) return; // the window puts the app in place twice; one shell
    const log = this.querySelector(".log"), box = Object.assign(document.createElement("div"), { className: "shell" });
    const tabs = Object.assign(document.createElement("div"), { className: "chips", innerHTML: `<button data-view="shell">Shell</button><button data-view="log">Commands</button>` });
    this.querySelector(".note").textContent = "Commands the skills hand to the device show up here. You can type one too: only the forms a skill declares are run (try “df -h /” or “free -h”).";
    this.prepend(tabs, box);
    await loadXterm();
    if (!box.isConnected) return;
    const term = new window.Terminal({ fontFamily: "'Departure Mono', ui-monospace, monospace", fontSize: 13, cursorBlink: true, theme: colours() });
    const fit = new window.FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(box);
    const ws = new WebSocket(location.origin.replace(/^http/, "ws") + "/api/shell");
    ws.binaryType = "arraybuffer";
    const send = m => { if (ws.readyState === 1) ws.send(JSON.stringify(m)); };
    const size = () => {
      if (!box.offsetWidth) return; // the log is in front
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
    document.addEventListener("themechange", onTheme);
    const view = name => {
      box.hidden = name !== "shell";
      log.hidden = name === "shell";
      for (const b of tabs.children) b.setAttribute("aria-pressed", b.dataset.view === name);
      if (name === "shell") { size(); term.focus(); }
    };
    tabs.addEventListener("click", e => { if (e.target.dataset.view) view(e.target.dataset.view); });
    view("shell");
    this.leave = () => { document.removeEventListener("themechange", onTheme); watch.disconnect(); ws.close(); term.dispose(); };
  }
}
customElements.define("app-terminal", AppTerminal);
