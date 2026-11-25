// A window, with the symbios chrome (.win, .win-head, .win-body): a title bar to drag, maximise
// and close, and the app inside. Size comes from the browser's resize corner; on a small
// screen the stylesheet makes it fill the screen and dragging does nothing.
import { I } from "../icons.js";
let top = 10;

class DeskWindow extends HTMLElement {
  connectedCallback() {
    if (this.querySelector(".win-head")) return;
    const app = this.firstElementChild;
    this.classList.add("win");
    this.innerHTML = `<div class="win-head"><div class="win-title">${I[this.getAttribute("app")] || ""}<span></span></div>
      <div class="win-ctrl"><button class="win-btn maxb" title="Maximize">${I.max}</button>
      <button class="win-btn close" title="Close">${I.close}</button></div></div>
      <div class="win-body"></div>`;
    this.querySelector(".win-title span").textContent = this.getAttribute("name");
    this.querySelector(".win-body").append(app);
    const head = this.querySelector(".win-head");
    this.querySelector(".close").addEventListener("click", () => this.close());
    this.querySelector(".maxb").addEventListener("click", () => this.classList.toggle("maxed"));
    head.addEventListener("dblclick", () => this.classList.toggle("maxed"));
    head.addEventListener("pointerdown", e => this.drag(e, head));
    this.addEventListener("pointerdown", () => this.focusWindow(), true);
    this.focusWindow();
  }
  focusWindow() {
    for (const w of this.parentElement.children) w.classList.toggle("focused", w === this);
    this.style.zIndex = ++top;
    this.dispatchEvent(new Event("desk:change", { bubbles: true }));
  }
  close() {
    const parent = this.parentElement;
    this.remove();
    parent.lastElementChild?.focusWindow();
    parent.dispatchEvent(new Event("desk:change", { bubbles: true }));
  }
  drag(e, head) {
    if (e.target.closest("button") || this.classList.contains("maxed") || matchMedia("(max-width: 760px)").matches) return;
    const dx = e.clientX - this.offsetLeft, dy = e.clientY - this.offsetTop;
    head.setPointerCapture(e.pointerId);
    const move = m => {
      this.style.left = Math.max(-this.offsetWidth + 80, Math.min(innerWidth - 80, m.clientX - dx)) + "px";
      this.style.top = Math.max(0, Math.min(innerHeight - 40, m.clientY - dy)) + "px";
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", () => head.removeEventListener("pointermove", move), { once: true });
  }
}
customElements.define("desk-window", DeskWindow);
