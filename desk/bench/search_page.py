"""A test page for search_bench.py: ask the board's articles and memos in a browser (Gab, 2026-10-23: "we could use it
for testing purposes"). Not the desk: its own port, the model loaded once, nothing written anywhere.

    PYTHONPATH=py python3 search_page.py HOME [PORT]    # then http://<board>:8091/

It reads the vector files search_lite.py writes, one per document (since 2026-10-23, Gab: "yes do all 3"); a
document synced later shows up when the page is started again.

GET /search?q=… answers the ten best documents with their scores; the page keeps those above the floor
(a slider, so the floor can be tried live) and says "not here" when none is left.
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import search_lite

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Search bench</title>
<style>
  :root { --bg: #f6f5f1; --ink: #1d1d1b; --soft: #6b6a65; --line: #dddbd3; --card: #fff; --accent: #2f5d50; --dim: #b9b7ae; }
  @media (prefers-color-scheme: dark) { :root { --bg: #161615; --ink: #ecebe6; --soft: #a19f97; --line: #33322f; --card: #1f1f1d; --accent: #8cc4b0; --dim: #55534e; } }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font: 16px/1.5 system-ui, sans-serif; }
  main { max-width: 760px; margin: 0 auto; padding: 24px 16px 64px; }
  h1 { font-size: 20px; margin: 0 0 4px; } .sub { color: var(--soft); font-size: 14px; margin: 0 0 20px; }
  form { display: flex; gap: 8px; } input[type=search] { flex: 1; font: inherit; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--card); color: var(--ink); }
  button { font: inherit; padding: 10px 16px; border: 0; border-radius: 8px; background: var(--accent); color: var(--bg); cursor: pointer; }
  .floor { display: flex; align-items: center; gap: 10px; margin: 14px 0 6px; color: var(--soft); font-size: 14px; flex-wrap: wrap; }
  .floor input { flex: 1; min-width: 140px; } .floor b { color: var(--ink); font-variant-numeric: tabular-nums; }
  .status { color: var(--soft); font-size: 13px; margin: 6px 0 16px; min-height: 1.5em; }
  .none { padding: 18px; border: 1px dashed var(--line); border-radius: 10px; color: var(--soft); }
  .hit { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; margin: 0 0 10px; }
  .hit.below { opacity: .45; } .top { display: flex; gap: 10px; align-items: baseline; }
  .score { font-variant-numeric: tabular-nums; font-weight: 600; min-width: 3.2em; }
  .kind { font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: var(--soft); }
  .title { font-weight: 600; } .title a { color: var(--accent); text-decoration: none; } .title a:hover { text-decoration: underline; }
  .para { color: var(--soft); font-size: 14px; margin: 6px 0 0; }
  .ranks { font-size: 12px; color: var(--soft); margin-top: 6px; }
  label.show { font-size: 13px; color: var(--soft); display: block; margin: 12px 0 6px; }
</style></head>
<body><main>
  <h1>Search bench</h1>
  <p class="sub">The board's articles and memos, searched by meaning (MiniLM) and keywords, one vector file per document. A test, not the desk.</p>
  <form id="f"><input type="search" id="q" placeholder="does AI impact democracy?" autofocus><button>Ask</button></form>
  <div class="floor">Floor <input type="range" id="floor" min="0.15" max="0.70" step="0.01" value="0.32"> <b id="fv">0.32</b></div>
  <div class="status" id="status"></div>
  <div id="hits"></div>
  <label class="show"><input type="checkbox" id="below"> show what falls below the floor</label>
  <div id="rest"></div>
</main>
<script>
const $ = id => document.getElementById(id);
let last = null;
function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
function card(r, below) {
  const c = el("div", "hit" + (below ? " below" : ""));
  const top = el("div", "top");
  top.append(el("span", "score", r.cos.toFixed(3)), el("span", "kind", r.kind));
  const t = el("span", "title");
  if (r.url) { const a = el("a", null, r.title); a.href = r.url; a.target = "_blank"; a.rel = "noopener"; t.append(a); } else t.textContent = r.title;
  top.append(t); c.append(top, el("p", "para", r.para));
  c.append(el("div", "ranks", "meaning #" + r.meaning + " · keywords " + (r.kw ? "#" + r.kw : "none") + (r.kind === "memo" ? " · ~/Memos/" + r.file : "")));
  return c;
}
function draw() {
  const floor = parseFloat($("floor").value); $("fv").textContent = floor.toFixed(2);
  $("hits").replaceChildren(); $("rest").replaceChildren();
  if (!last) return;
  const above = last.results.filter(r => r.cos >= floor).slice(0, 5), under = last.results.filter(r => r.cos < floor);
  if (!above.length) $("hits").append(el("div", "none", "Not here: nothing in the articles or memos is about this. Best score " + Math.max(...last.results.map(r => r.cos)).toFixed(3) + ", floor " + floor.toFixed(2) + "."));
  above.forEach(r => $("hits").append(card(r, false)));
  if ($("below").checked) under.forEach(r => $("rest").append(card(r, true)));
}
$("f").onsubmit = async e => {
  e.preventDefault(); const q = $("q").value.trim(); if (!q) return;
  $("status").textContent = "Searching…";
  try {
    const r = await fetch("search?q=" + encodeURIComponent(q)); last = await r.json();
    $("status").textContent = last.results.length + " documents scored in " + last.ms + " ms";
  } catch (err) { $("status").textContent = "The bench didn't answer: " + err; last = null; }
  draw();
};
$("floor").oninput = draw; $("below").onchange = draw;
</script></body></html>"""


def main(home, port=8091):
    lib = search_lite.Library(home)  # each article's address is in its vector file

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                body, kind = PAGE.encode(), "text/html; charset=utf-8"
            elif url.path == "/search":
                q = parse_qs(url.query).get("q", [""])[0][:300]
                t = time.time()
                found = lib.search(q) if q.strip() else []
                found = found[:10] + [f for f in found[10:] if f["meaning"] == 1]  # the best by meaning: what the floor is held against
                body = json.dumps({"q": q, "ms": round(1000 * (time.time() - t)), "results": [
                    {"title": lib.docs[f["doc"]]["title"], "kind": lib.docs[f["doc"]]["kind"], "file": lib.docs[f["doc"]]["file"],
                     "url": lib.docs[f["doc"]].get("url", ""), "cos": round(f["cos"], 4), "meaning": f["meaning"], "kw": f["kw"],
                     "para": lib.chunks[f["para"]]["text"][:400]} for f in found]}).encode()
                kind = "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print("search page on port %d" % port, flush=True)
    HTTPServer(("", port), Handler).serve_forever()  # one at a time: the search's SQLite stays on its own thread


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8091)
