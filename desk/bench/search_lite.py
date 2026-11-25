"""search_bench.py stored as brainboard stores it: one vector file per document, written once (Gab, 2026-10-23: the
hidden folder "is clever and dead simple"; "build this way and compare the accuracy of the answers per question").
Since 2026-10-23 the desk writes those files itself (embed.py, on the worker's rounds, long paragraphs cut at sentence
ends); this reads them to ask questions, and `sync` does at once what the worker does over its rounds.

    ~/Memos/<memo>/.vectors.json          beside the transcript: it goes when the memo's folder goes
    ~/Articles/.vectors/<article>.json    named after the article: dropped at load when the article is gone

Each file holds the document's title, link and passages, their vectors as int8 (base64, brainboard's pack.js:
round(v * 127), the question kept as float), a fingerprint of the recipe and a hash of the source text. It is
written when its document is new or changed, never otherwise. Keywords: BM25 computed in memory from those passages
when the library loads (brainboard's lexical.js), no SQLite. The cleaning, the model and the ranking are
search_bench.py's own, so a comparison measures only what changed: int8 vectors and the keyword index.

    python3 search_lite.py sync HOME                        # embed what is new or changed, drop what is gone
    python3 search_lite.py ask HOME "question" [FLOOR]
    python3 search_lite.py compare HOME OUT questions.json  # question by question, against search_bench's index in OUT

That index was deleted from the board once the comparison held (Gab, 2026-10-23); `search_bench.py index HOME OUT`
builds it again (~5 min on the board).
"""
import base64
import json
import math
import os
import re
import sys
import time
from collections import Counter

import numpy as np

import search_bench  # puts the desk's own folder on the path, for embed and wordpiece

import embed  # the desk's embedding (since 2026-10-23): the cut, the vector files, the recipe

FINGERPRINT = embed.FINGERPRINT  # the files the desk writes; another recipe is left out until it is redone
DIM, SCALE = embed.DIM, embed.SCALE
TITLE = 2  # the title counts twice, as search_bench's bm25(p, 2.0, 1.0)
K1, B = 1.2, 0.75  # SQLite FTS5's own BM25 constants
STOP = search_bench.STOP


def sources(home):
    """Every article, and every memo once transcribed, as the desk embeds them: (kind, name, source, vector file)."""
    for src, dst in embed.documents(home):
        kind = embed.where(src)[0]
        yield kind, os.path.basename(os.path.dirname(src) if kind == "memo" else src), src, dst


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


orphans = embed.orphans


def sync(home):
    """What the desk's worker does on its rounds, here at once: every document that waits, embedded (embed.py)."""
    t0, n, done = time.time(), 0, 0
    todo = embed.waiting(home)
    for src, dst in todo:
        n += embed.embed(src)
        done += 1
    gone = orphans(home)
    print("%d embedded (%d passages), %d unchanged, %d removed; %.1f s"
          % (done, n, len(embed.documents(home)) - done, len(gone), time.time() - t0))


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
    """Every vector file, loaded; a file of another recipe is left out until sync redoes it."""

    def __init__(self, home, embed=None):
        orphans(home)
        self.docs, self.chunks, rows = [], [], []
        for kind, name, src, dst in sources(home):
            rec = read(dst)
            if not rec or rec.get("fingerprint") != FINGERPRINT:
                continue
            di = len(self.docs)
            self.docs.append({"kind": kind, "file": name, "title": rec["title"], "url": rec.get("url", "")})
            self.chunks += [{"doc": di, "text": c} for c in rec["chunks"]]
            rows.append(np.frombuffer(base64.b64decode(rec["vecs64"]), np.int8).reshape(-1, DIM))
        self.vecs = (np.concatenate(rows) if rows else np.zeros((0, DIM), np.int8)).astype(np.float32) / SCALE
        self.of = np.array([c["doc"] for c in self.chunks])
        # BM25 postings: word → [(passage, count)], the title's words counted TITLE times more
        self.post, self.len = {}, []
        for i, c in enumerate(self.chunks):
            tf = Counter(words(c["text"]) + words(self.docs[c["doc"]]["title"]) * TITLE)
            self.len.append(sum(tf.values()))
            for w, f in tf.items():
                self.post.setdefault(w, []).append((i, f))
        self.avg = sum(self.len) / max(len(self.len), 1)
        self.embed = embed or search_bench.encoder()

    def keywords(self, question, limit=200):
        n, score = len(self.chunks), Counter()
        for w in set(words(question)):
            hits = self.post.get(w, [])
            idf = math.log(1 + (n - len(hits) + 0.5) / (len(hits) + 0.5))
            for i, f in hits:
                score[i] += idf * f * (K1 + 1) / (f + K1 * (1 - B + B * self.len[i] / self.avg))
        return [i for i, _ in score.most_common(limit)]

    def search(self, question):
        """The same ranking as search_bench.Library.search(), on these vectors and this keyword index."""
        cos = self.vecs @ self.embed([question])[0]
        best = {}
        for i in np.argsort(-cos):
            best.setdefault(int(self.of[i]), (float(cos[i]), int(i)))
        meaning = sorted(best, key=lambda d: -best[d][0])
        keyword = []
        for i in self.keywords(question):
            if int(self.of[i]) not in keyword:
                keyword.append(int(self.of[i]))
        fused = {d: 1 / (60 + meaning.index(d) + 1) + (1 / (60 + keyword.index(d) + 1) if d in keyword else 0) for d in best}
        order = sorted(best, key=lambda d: -fused[d])
        return [{"doc": d, "cos": best[d][0], "para": best[d][1], "kw": keyword.index(d) + 1 if d in keyword else None,
                 "meaning": meaning.index(d) + 1} for d in order]


def ask(home, question, floor=None):
    t0 = time.time()
    lib = Library(home)
    t1 = time.time()
    found = lib.search(question)
    print("loading %.2f s, question %.2f s" % (t1 - t0, time.time() - t1))
    shown = [f for f in found if floor is None or f["cos"] >= float(floor)][:5]
    if not shown:
        print("not here: nothing in the articles or memos is about this (best %.3f, floor %s)" % (found[0]["cos"], floor))
    for f in shown:
        d = lib.docs[f["doc"]]
        print("%.3f  %-7s %s  (meaning #%d, keywords %s)" % (f["cos"], d["kind"], d["title"][:70], f["meaning"],
                                                          "#%d" % f["kw"] if f["kw"] else "-"))


def compare(home, out, questions):
    """Each question asked of both: where the right documents land, the best score, and the first five."""
    t0 = time.time()
    old = search_bench.Library(out)
    t1 = time.time()
    new = Library(home, embed=old.embed)  # one model: the same question vector for both
    t2 = time.time()
    print("loading: bench %.2f s (model included), one file per document %.2f s" % (t1 - t0, t2 - t1))
    print("documents: bench %d, one file per document %d; passages %d and %d"
          % (len(old.docs), len(new.docs), len(old.chunks), len(new.chunks)))
    rows = []
    for q in json.load(open(questions, encoding="utf-8"))["questions"]:
        r = {"q": q["q"], "kind": q["kind"]}
        for side, lib in (("old", old), ("new", new)):
            found = lib.search(q["q"])
            names = [lib.docs[f["doc"]]["file"] for f in found]
            r[side] = {"best": max(f["cos"] for f in found), "five": names[:5],  # what the floor is held against
                       "right": [i + 1 for i, n in enumerate(names) if any(n.startswith(x) for x in q.get("right", []))]}
        rows.append(r)
    print("\n%-52s %-16s %-16s %s" % ("question", "bench", "one file", "first five"))
    for r in rows:
        o, n = r["old"], r["new"]
        def where(s):
            return "%.3f %s" % (s["best"], ",".join("#%d" % i for i in s["right"][:3]) or "-")
        same = "same" if o["five"] == n["five"] else "%d of 5 shared" % len(set(o["five"]) & set(n["five"]))
        print("%-52s %-16s %-16s %s" % ((r["kind"][0] + " " + r["q"])[:52], where(o), where(n), same))
    for side, label in (("old", "bench"), ("new", "one file per document")):
        ans = [r[side] for r in rows if r["kind"] == "answerable"]
        top = {k: [r[side]["best"] for r in rows if r["kind"] == k] for k in ("answerable", "near-miss", "off-topic")}
        print("\n%s: right document first %d/%d, in the first 3 %d/%d; weakest answer %.3f, strongest off-topic %.3f, "
              "strongest near-miss %.3f" % (label, sum(1 in a["right"] for a in ans), len(ans),
                                            sum(any(i <= 3 for i in a["right"]) for a in ans), len(ans),
                                            min(top["answerable"]), max(top["off-topic"]), max(top["near-miss"])))
    d = [abs(r["old"]["best"] - r["new"]["best"]) for r in rows]
    print("\nbest score moved by %.4f on average, %.4f at most; the first five identical for %d of %d questions"
          % (sum(d) / len(d), max(d), sum(r["old"]["five"] == r["new"]["five"] for r in rows), len(rows)))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "sync":
        sync(sys.argv[2])
    elif cmd == "ask":
        ask(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "compare":
        compare(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(__doc__)
