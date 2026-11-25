// The file explorer, with the symbios markup and styles (.explorer): the folder on the left,
// the selected file on the right. It lists the home folder the skills work in.
import { bus, list, read } from "../services/device.js";

const fmtSize = n => (n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(1) + " K" : (n / 1048576).toFixed(1) + " M");
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls, textContent: text || "" });

class AppFiles extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="explorer">
      <div class="bar"><button class="home" title="Home">⌂</button><button class="up" title="Up">↑</button><span class="path"></span></div>
      <div class="cols"><div class="list"></div>
        <div class="view"><div class="vhead"><span class="vname">Select a file</span><button type="button" class="edit" hidden>Edit</button></div><div class="vbody"></div></div></div></div>`;
    this.pathEl = this.querySelector(".path");
    this.listEl = this.querySelector(".list");
    this.vname = this.querySelector(".vname");
    this.vbody = this.querySelector(".vbody");
    this.edit = this.querySelector(".edit");
    this.edit.addEventListener("click", () => bus.dispatchEvent(new CustomEvent("open", { detail: { app: "editor", path: this.shown } })));
    this.querySelector(".home").addEventListener("click", () => this.open(""));
    this.querySelector(".up").addEventListener("click", () => this.open(this.path.split("/").slice(0, -1).join("/")));
    this.onFiles = () => this.open(this.path).then(() => this.shown && this.show(this.shown));
    bus.addEventListener("files", this.onFiles);
    this.open(this.getAttribute("path") || "");
  }
  disconnectedCallback() { bus.removeEventListener("files", this.onFiles); }
  msg(text) { this.vbody.replaceChildren(el("div", "msg", text)); }
  // a folder is listed; anything else is shown as a file inside its folder
  async open(path) {
    try {
      const d = await list(path);
      this.path = path;
      this.pathEl.textContent = "~/" + path;
      this.listEl.replaceChildren(...d.entries.map(e => {
        const item = el("div", "item" + (e.dir ? " dir" : ""));
        item.append(el("span", "ic", e.dir ? "▸" : "·"), el("span", "nm", e.name), el("span", "sz", e.dir ? "" : fmtSize(e.size)));
        const full = (path ? path + "/" : "") + e.name;
        item.addEventListener("click", () => (e.dir ? this.open(full) : this.show(full)));
        return item;
      }));
    } catch (err) {
      if (err.message !== "not found") return this.msg(err.message);
      const parent = path.split("/").slice(0, -1).join("/");
      if (parent !== path) await this.open(parent);
      this.show(path);
    }
  }
  async show(path) {
    this.vname.textContent = path.split("/").pop();
    this.shown = path;
    try { this.vbody.replaceChildren(el("pre", "", (await read(path)).text || "(empty file)")); this.edit.hidden = false; }
    catch (e) { this.shown = null; this.edit.hidden = true; this.msg(e.message === "not found" ? "There is no “" + path + "” here." : e.message); }
  }
}
customElements.define("app-files", AppFiles);
