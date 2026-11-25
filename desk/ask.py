"""ask: a question → the articles and memos on the board that are about it, or "not here" (Gab, 2026-10-23: an Ask
window on the desk, the model kept loaded). A small service of its own, started by the desk server under the job
limits, so the desk server never loads the model; the desk asks it on 127.0.0.1 (GET /ask?q=…), the desk's own
/api/ask passes the answer on, to the Ask window and later to the phone.

How it answers, measured on the board on 2026-10-23 (brain: knowledge/retrieval/minilm-search-on-orange-pi-zero-2w.md
and one-vector-file-per-document-on-orange-pi-zero-2w.md): the question goes through MiniLM (embed.encoder) and is
compared with every passage embed.py wrote (cosine; a document counts by its best passage); the same passages are
ranked by their words too (BM25, brainboard's lexical.js, the title counted twice); the two orders are joined by
rank, 1/(60 + rank). A document is shown only if its best passage reaches FLOOR: below it, "not here". Right
document first for 23 of 24 questions, every off-topic question refused; a near miss (the topic is there, not the
answer) is not. ~30 ms a question; ~80 MB held.

A document embedded since the last question is read before the next one: the vector files are looked at (their
times only) at each question.

    python3 ask.py HOME [PORT]    # serve on 127.0.0.1:PORT (default 8801)
"""
import base64
import json
import math
import os
import re
import sys
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import embed
import jobs

PORT = 8801
FLOOR = 0.32  # cosine: real answers on the board reach 0.38, off-topic questions stay under 0.30 (2026-10-23)
SHOWN = 5  # documents at most
TITLE = 2  # a title word counts twice
K1, B = 1.2, 0.75  # BM25, as SQLite's FTS5
STOP = set("a an the and or but of to for in on at by from with is are was were be been do does did how what which who "
           "whom why when where can could should would will i my me you your we our it its this that there their about "
           "any some as if not no".split())


def stem(w):
    """brainboard's light stemmer (lexical.js): the question and the passages meet on the same key."""
    s = w
    if len(s) > 4:
        if s.endswith("ies"):
            s = s[:-3] + "y"
        elif s.endswith("sses"):
            s = s[:-2]
        elif s.endswith("s") and not s.endswith(("ss", "us")):
            s = s[:-1]
    if len(s) > 5:
        for end in ("ing", "edly", "ed", "ly"):
            if s.endswith(end):
                s = s[:-len(end)]
                break
    return s[:-1] if len(s) > 4 and s.endswith("e") else s


def words(text):
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in STOP]


class Library:
    """Every vector file the desk wrote, loaded, and read again when one of them changes."""

    def __init__(self, home):
        self.vector = embed.encoder()  # first: it puts the board's numpy and onnxruntime on the path
        import numpy as np
        self.np, self.home, self.seen = np, home, None

    def fresh(self):
        """The files read again if any was added, changed or removed since the last question."""
        files = embed.documents(self.home)
        seen = []
        for src, dst in files:
            try:
                seen.append((dst, os.path.getmtime(dst)))
            except OSError:
                pass
        if seen == self.seen:
            return
        np = self.np
        self.seen, self.docs, self.chunks, rows = seen, [], [], []
        for src, dst in files:
            try:
                with open(dst, encoding="utf-8") as f:
                    rec = json.load(f)
            except (OSError, ValueError):
                continue
            if rec.get("fingerprint") != embed.FINGERPRINT:
                continue  # of another recipe: the worker is redoing it
            di = len(self.docs)
            doc = {"kind": rec["kind"], "title": rec["title"], "url": rec.get("url", ""), "path": os.path.relpath(src, self.home)}
            if rec["kind"] == "memo":
                # a memo is its folder with its sound, as Files gives it: the Player plays the sound, the Reader opens
                # the folder's transcript.md (its transcript.md alone played nothing and was read as
                # transcript.md/transcript.md, Gab, 24 Nov: "the URL of the memo is broken everywhere")
                folder = os.path.dirname(src)
                doc["path"] = os.path.relpath(folder, self.home)
                try:
                    sound = next((n for n in sorted(os.listdir(folder)) if n.startswith("audio.")), None)
                except OSError:
                    sound = None
                if sound:
                    doc["audio"] = doc["path"] + "/" + sound
            self.docs.append(doc)
            self.chunks += [{"doc": di, "text": c} for c in rec["chunks"]]
            rows.append(np.frombuffer(base64.b64decode(rec["vecs64"]), np.int8).reshape(-1, embed.DIM))
        self.vecs = (np.concatenate(rows) if rows else np.zeros((0, embed.DIM), np.int8)).astype(np.float32) / embed.SCALE
        self.of = np.array([c["doc"] for c in self.chunks], dtype=int)
        self.post, self.len = {}, []  # BM25: word → [(passage, count)]
        for i, c in enumerate(self.chunks):
            tf = Counter(words(c["text"]) + words(self.docs[c["doc"]]["title"]) * TITLE)
            self.len.append(sum(tf.values()))
            for w, n in tf.items():
                self.post.setdefault(w, []).append((i, n))
        self.avg = sum(self.len) / max(len(self.len), 1)

    def keywords(self, question, limit=200):
        n, score = len(self.chunks), Counter()
        for w in set(words(question)):
            hits = self.post.get(w, [])
            idf = math.log(1 + (n - len(hits) + 0.5) / (len(hits) + 0.5))
            for i, f in hits:
                score[i] += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
        return [i for i, _ in score.most_common(limit)]

    def answer(self, question):
        """{results: the documents above the floor, best first; best: the highest cosine of all; floor}."""
        self.fresh()
        if not self.chunks:
            return {"results": [], "best": None, "floor": FLOOR}
        cos = self.vecs @ self.vector(question)
        best = {}
        for i in self.np.argsort(-cos):
            best.setdefault(int(self.of[i]), (float(cos[i]), int(i)))
        meaning = sorted(best, key=lambda d: -best[d][0])
        keyword = []
        for i in self.keywords(question):
            if int(self.of[i]) not in keyword:
                keyword.append(int(self.of[i]))
        fused = {d: 1 / (61 + meaning.index(d)) + (1 / (61 + keyword.index(d)) if d in keyword else 0) for d in best}
        shown = [d for d in sorted(best, key=lambda d: -fused[d]) if best[d][0] >= FLOOR][:SHOWN]
        return {"floor": FLOOR, "best": round(best[meaning[0]][0], 3), "results": [
            {**self.docs[d], "score": round(best[d][0], 3), "passage": self.chunks[best[d][1]]["text"]} for d in shown]}


def serve(home, port=PORT):
    lib = Library(home)
    lib.fresh()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            if url.path != "/ask":
                return self.send_error(404)
            q = parse_qs(url.query).get("q", [""])[0].strip()[:300]
            t = time.time()
            out = lib.answer(q) if q else {"results": [], "best": None, "floor": FLOOR}
            body = json.dumps({"q": q, "ms": round(1000 * (time.time() - t)), **out}, ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    print("ask: %d documents, %d passages, on 127.0.0.1:%d" % (len(lib.docs), len(lib.chunks), port), flush=True)
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()  # one question at a time


UNIT = "desk-ask"


def running():
    """Whether the service is up, or still loading."""
    import subprocess
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", UNIT], timeout=10).returncode == 0


def start(home, port=PORT):
    """The service, (re)started under the job limits, with this server's code; nothing when MiniLM isn't here.
    It takes no heavy lock: a question is ~30 ms, and isn't held behind a transcription. Answers whether it runs."""
    import subprocess
    if not os.path.isfile(os.path.join(embed.MODEL, "model_quantized.onnx")):
        return False
    subprocess.run(["systemctl", "--user", "stop", UNIT], capture_output=True, timeout=30)
    subprocess.run(["systemctl", "--user", "reset-failed", UNIT], capture_output=True, timeout=30)  # a failed one keeps its name
    env = ["-E", "DESK_MODELS=" + os.environ["DESK_MODELS"]] if "DESK_MODELS" in os.environ else []
    r = subprocess.run(["systemd-run", "--user", "--quiet", "--unit", UNIT, *jobs.limits("ask"), "-p", "Nice=19", *env,
                        sys.executable, os.path.abspath(__file__), os.path.realpath(home), str(port)],
                       capture_output=True, text=True, timeout=30)
    if r.returncode:
        sys.stderr.write("ask: not started: %s\n" % (r.stderr.strip() or "?"))
    return r.returncode == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    serve(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else PORT)
