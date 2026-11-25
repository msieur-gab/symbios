// Info: a file no app on the desk reads yet: its name, size and date, and a copy to save.
import { I } from "../../shared/icons.js";
import { raw } from "../../shared/api.js";
import { size } from "../../utils/format.js";
import { titled } from "../../shared/desk.js";

class AppInfo extends HTMLElement {
  show(item) {
    this.path = item.path;
    this.innerHTML = `<div class="info"><span class="glyph">${I.file}</span><b></b><small></small><p>No app on the desk reads this kind of file yet.</p><a download>Save a copy</a></div>`;
    this.querySelector("b").textContent = item.path.split("/").pop();
    this.querySelector("small").textContent = [size(item.size), item.modified && new Date(item.modified).toLocaleString()].filter(Boolean).join(" · ");
    this.querySelector("a").href = raw(item.path);
    titled(this, item);
  }
}

export default {
  id: "info",
  name: "Info",
  icon: I.file,
  size: [360, 280],
  many: true,
  opens: ["file"],
  element: AppInfo,
};
