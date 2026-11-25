// A plain text editor for the files of the home folder: open, change, save (button or Ctrl+S).
// One file at a time; opening another one asks nothing and replaces it once saved text is safe.
import { bus, read, write } from "../services/device.js";

class AppEditor extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<form class="entry"><span></span><button disabled>Save</button></form>
      <textarea class="editor" spellcheck="false" aria-label="File contents"></textarea>`;
    this.label = this.querySelector("span");
    this.area = this.querySelector("textarea");
    this.button = this.querySelector("button");
    this.area.addEventListener("input", () => this.mark(true));
    this.querySelector("form").addEventListener("submit", e => { e.preventDefault(); this.save(); });
    this.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); this.save(); } });
    this.open(this.getAttribute("path"));
  }
  mark(changed, note) {
    this.changed = changed;
    this.button.disabled = !changed || !this.path;
    this.label.textContent = this.path ? "~/" + this.path + (note ? " · " + note : changed ? " · not saved" : "") : "Open a file from Files, or say “create a file called notes.md”.";
  }
  async open(path) {
    if (this.changed && this.path && this.path !== path) await this.save(); // don't lose what was typed
    this.path = path || "";
    this.area.value = "";
    this.area.disabled = !this.path;
    if (!this.path) return this.mark(false);
    try {
      this.area.value = (await read(this.path)).text;
      this.mark(false);
      this.area.focus({ preventScroll: true });
    } catch (e) {
      this.area.disabled = true;
      this.mark(false, e.message === "not found" ? "there is no such file" : e.message);
    }
  }
  async save() {
    if (!this.path || !this.changed) return;
    try { await write(this.path, this.area.value); this.mark(false, "saved"); bus.dispatchEvent(new CustomEvent("files")); }
    catch (e) { this.mark(true, "not saved: " + e.message); }
  }
}
customElements.define("app-editor", AppEditor);
