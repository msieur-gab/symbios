// Document: a PDF of the home, shown by the browser's own reader.
import { I } from "../../shared/icons.js";
import { raw } from "../../shared/api.js";
import { titled } from "../../shared/desk.js";

class AppDocument extends HTMLElement {
  show(item) {
    this.path = item.path;
    this.innerHTML = `<iframe title="" src="${raw(item.path)}"></iframe>`;
    titled(this, item);
  }
}

export default {
  id: "document",
  name: "Document",
  icon: I.document,
  size: [720, 660],
  many: true,
  opens: ["document"],
  element: AppDocument,
};
