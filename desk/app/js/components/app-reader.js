// The reader: the articles the board keeps in ~/Articles (article.py makes them), as a library
// and, one at a time, as a page to read. Look and classes are symbios's Reader (.reader, .home,
// .doc); the markdown is drawn by marked (vendored, as on symbios) and cleaned of anything that
// runs, since it comes from the web. A link typed in the bar is kept, then opened.
import { bus, read, article, articles } from "../services/device.js";

let marked; // window.marked, loaded with the first article
const loadMarked = () => marked ||= new Promise((ok, no) => document.head.append(Object.assign(document.createElement("script"), { src: "vendor/marked.min.js", onload: ok, onerror: no })));
const el = (tag, cls, text) => Object.assign(document.createElement(tag), { className: cls || "", textContent: text || "" });

// a kept article → its front matter (as article.py writes it) and its markdown
function split(text) {
  const head = /^---\n([\s\S]*?)\n---\n?/.exec(text), card = {};
  for (const line of head ? head[1].split("\n") : []) {
    const at = line.indexOf(": ");
    if (at < 1) continue;
    const value = line.slice(at + 2);
    try { card[line.slice(0, at)] = /^["[]/.test(value) ? JSON.parse(value) : value; } catch { card[line.slice(0, at)] = value; }
  }
  return { card, body: head ? text.slice(head[0].length) : text };
}

// markdown → nodes, with nothing executable left (as symbios's Notes does); links open outside the desk
function draw(md) {
  const box = el("div");
  box.innerHTML = window.marked.parse(md || "", { gfm: true });
  // as the new desk's shared/clean.js (symbios SECURITY.md, review of 24 Nov, C2): links read as the browser reads them
  box.querySelectorAll("script,style,iframe,frame,frameset,object,embed,applet,form,input,button,textarea,select,link,meta,base,svg,math,map,area,template,noscript,portal").forEach(e => e.remove());
  const safe = v => { try { return ["http:", "https:", "mailto:"].includes(new URL(v, location.href).protocol); } catch { return false; } };
  const links = ["href", "src", "xlink:href", "action", "formaction", "cite", "poster", "background", "data", "usemap", "longdesc"];
  for (const e of box.querySelectorAll("*")) {
    for (const a of [...e.attributes]) {
      const n = a.name.toLowerCase();
      if (n.startsWith("on") || n === "srcset" || n === "formtarget" || (links.includes(n) && !safe(a.value))) e.removeAttribute(a.name);
    }
    if (e.tagName === "A") Object.assign(e, { target: "_blank", rel: "noopener noreferrer" });
    if (e.tagName === "IMG") Object.assign(e, { loading: "lazy", referrerPolicy: "no-referrer" });
  }
  return box;
}

class AppReader extends HTMLElement {
  connectedCallback() {
    this.innerHTML = `<div class="reader"><form class="bar"><button type="button" data-do="home">Library</button>
      <input name="u" placeholder="Paste a link to keep its article" autocomplete="off" spellcheck="false" aria-label="Link"><button>Keep</button></form>
      <div class="body"><div class="doc"><div class="inner"></div></div></div></div>`;
    this.page = this.querySelector(".inner");
    this.querySelector("[data-do=home]").addEventListener("click", () => this.open(""));
    this.querySelector("form").addEventListener("submit", e => {
      e.preventDefault();
      const u = e.target.u;
      if (u.value.trim()) this.keep(u.value.trim());
      u.value = "";
    });
    this.onFiles = () => { if (!this.path) this.home(); };
    bus.addEventListener("files", this.onFiles);
    this.open(this.getAttribute("path"));
  }
  disconnectedCallback() { bus.removeEventListener("files", this.onFiles); }
  say(text) { this.page.replaceChildren(el("div", "status", text)); }
  // a path ("Articles/….md") shows that article; none shows the library
  open(path) {
    this.path = path || "";
    this.querySelector(".doc").scrollTop = 0;
    return this.path ? this.show() : this.home();
  }
  async home() {
    let list;
    try { list = await articles(); } catch (e) { return this.say("The library can't be read: " + e.message + "."); }
    if (this.path) return; // an article was opened meanwhile
    this.page.className = "inner home";
    this.page.replaceChildren(el("h3", "", "ARTICLES"));
    if (!list.length) this.page.append(el("div", "status", "Nothing kept yet. Paste a link above, or in the Assistant."));
    for (const a of list) {
      const row = el("a");
      row.append(el("div", "", a.title || a.file), el("div", "u", [a.siteName, a.author, a.published].filter(Boolean).join(" · ")));
      row.addEventListener("click", () => this.open("Articles/" + a.file));
      this.page.append(row);
    }
  }
  async show() {
    const path = this.path;
    this.say("Opening…");
    let text;
    try { [{ text }] = await Promise.all([read(path), loadMarked()]); } catch (e) { return this.say("That article can't be opened: " + e.message + "."); }
    if (path !== this.path) return;
    const { card, body } = split(text);
    this.page.className = "inner";
    this.page.replaceChildren(el("h1", "", card.title || path.split("/").pop()), el("p", "by", [card.author, card.siteName, card.published].filter(Boolean).join(" · ")));
    // the cover leads the page unless the article already shows it
    if (card.cover && !body.includes(card.cover.split("?")[0])) this.page.append(Object.assign(el("img"), { src: card.cover, alt: "", referrerPolicy: "no-referrer" }));
    this.page.append(...draw(body).childNodes);
    if (card.url) {
      const source = el("p", "by");
      source.append(Object.assign(el("a", "", "The page this was kept from"), { href: card.url, target: "_blank", rel: "noopener noreferrer" }));
      this.page.append(source);
    }
  }
  async keep(url) {
    this.path = "";
    this.say("Reading that page…");
    try { this.open((await article(url)).path); } catch (e) { this.say("Not kept: " + e.message + "."); }
  }
}
customElements.define("app-reader", AppReader);
