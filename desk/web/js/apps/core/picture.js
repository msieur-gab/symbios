// Picture: one picture of the home, given by Files or by the desktop; the others of its folder beside it.
import { I } from "../../shared/icons.js";
import { raw } from "../../shared/api.js";
import { titled } from "../../shared/desk.js";

class AppPicture extends HTMLElement {
  show(item, among) {
    this.list = (among || [item]).filter(i => i.kind === "picture");
    this.at = Math.max(0, this.list.findIndex(i => i.path === item.path));
    if (!this.img) {
      this.innerHTML = `<div class="pic"><img alt=""></div><div class="vbar"><button class="ib prev" title="Previous (←)">${I.prev}</button><span class="vname"></span><button class="ib next" title="Next (→)">${I.next}</button></div>`;
      this.img = this.querySelector("img");
      this.querySelector(".prev").onclick = () => this.go(-1);
      this.querySelector(".next").onclick = () => this.go(1);
      this.tabIndex = 0;
      this.addEventListener("keydown", e => { if (e.key === "ArrowLeft") this.go(-1); if (e.key === "ArrowRight") this.go(1); });
    }
    this.go(0);
  }
  get path() { return this.list?.[this.at]?.path; }
  go(step) {
    this.at = (this.at + step + this.list.length) % this.list.length;
    const item = this.list[this.at];
    this.img.src = raw(item.path);
    this.querySelector(".vname").textContent = `${this.at + 1} / ${this.list.length}`;
    this.querySelector(".prev").hidden = this.querySelector(".next").hidden = this.list.length < 2;
    titled(this, item);
    this.focus({ preventScroll: true });
  }
}

export default {
  id: "picture",
  name: "Picture",
  icon: I.picture,
  size: [680, 540],
  many: true,
  opens: ["picture"],
  element: AppPicture,
};
