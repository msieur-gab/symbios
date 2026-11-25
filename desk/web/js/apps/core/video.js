// Video: one video of the home, given by Files or by the desktop.
import { I } from "../../shared/icons.js";
import { raw } from "../../shared/api.js";
import { titled } from "../../shared/desk.js";

class AppVideo extends HTMLElement {
  show(item) {
    this.path = item.path;
    this.innerHTML = `<video controls autoplay playsinline></video>`;
    this.querySelector("video").src = raw(item.path);
    this.querySelector("video").onerror = () => { this.innerHTML = `<p class="empty">This film can't be played here.</p>`; };
    titled(this, item);
  }
  closing() { this.querySelector("video")?.pause(); }
}

export default {
  id: "video",
  name: "Video",
  icon: I.video,
  size: [760, 500],
  many: true,
  opens: ["video"],
  element: AppVideo,
};
