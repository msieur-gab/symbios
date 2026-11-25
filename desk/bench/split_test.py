"""A paragraph longer than MiniLM reads (256 tokens) cut at its sentence ends into pieces that fit, each with the
title in front, against the paragraph as one passage whose end is never embedded (Gab, 2026-10-23: "yes test the
sentence split and compare per question"). On the board, 35 of 784 passages were cut that way: 4.7 % of the text.

Nothing is written: the vector files are read as they are, only the split paragraphs are embedded (one at a time,
as search_lite.sync does), and the split library lives in memory.

    PYTHONPATH=~/.models/shared/python python3 split_test.py HOME questions.json
    (search_questions.json: the first set; split_questions.json: questions only the cut-off text answers)
"""
import copy
import json
import math
import os
import re
import sys
import time
from collections import Counter

import numpy as np

import search_bench
import search_lite
import wordpiece

LIMIT = 256  # tokens, [CLS] and [SEP] included: what the encoder reads
SENTENCE = re.compile(r"(?<=[.?!…])\s+")
TOK = wordpiece.Tokenizer(os.path.join(search_bench.MODEL, "tokenizer.json"), 10 ** 6)


def fits(title, text):
    return len(TOK.encode("%s. %s" % (title, text))) <= LIMIT


def split(title, text):
    """The paragraph as pieces that fit, cut only at sentence ends; a sentence too long alone stays one piece."""
    if fits(title, text):
        return [text]
    pieces, cur = [], ""
    for s in SENTENCE.split(text):
        trial = (cur + " " + s).strip()
        if cur and not fits(title, trial):
            pieces.append(cur)
            cur = s
        else:
            cur = trial
    return pieces + ([cur] if cur else [])


def rebuild(lib, chunks, vecs):
    """lib with other passages: its vectors and its BM25, built as search_lite.Library builds them."""
    new = copy.copy(lib)
    new.chunks, new.vecs = chunks, vecs
    new.of = np.array([c["doc"] for c in chunks])
    new.post, new.len = {}, []
    for i, c in enumerate(chunks):
        tf = Counter(search_lite.words(c["text"]) + search_lite.words(new.docs[c["doc"]]["title"]) * search_lite.TITLE)
        new.len.append(sum(tf.values()))
        for w, f in tf.items():
            new.post.setdefault(w, []).append((i, f))
    new.avg = sum(new.len) / max(len(new.len), 1)
    return new


def main(home, questions):
    old = search_lite.Library(home)
    t0, chunks, rows, cut, pieces, tail = time.time(), [], [], 0, 0, set()
    for i, c in enumerate(old.chunks):
        title = old.docs[c["doc"]]["title"]
        parts = split(title, c["text"])
        if len(parts) == 1:
            chunks.append(c)
            rows.append(old.vecs[i:i + 1])
            continue
        cut += 1
        v = old.embed(["%s. %s" % (title, p) for p in parts], batch=1)
        v = np.clip(np.round(v * search_lite.SCALE), -128, 127).astype(np.float32) / search_lite.SCALE  # as stored
        for k, p in enumerate(parts):
            if k:
                tail.add(len(chunks))  # a piece that was never embedded before
            chunks.append({"doc": c["doc"], "text": p})
        rows.append(v)
        pieces += len(parts)
    new = rebuild(old, chunks, np.concatenate(rows))
    print("%d paragraphs over %d tokens split into %d pieces (%d passages now, %d before); embedded in %.0f s"
          % (cut, LIMIT, pieces, len(chunks), len(old.chunks), time.time() - t0))
    still = sum(not fits(old.docs[c["doc"]]["title"], c["text"]) for c in chunks)
    print("passages still over the limit (one sentence too long alone): %d" % still)

    results = []
    for q in json.load(open(questions, encoding="utf-8"))["questions"]:
        r = {"q": q["q"], "kind": q["kind"]}
        for side, lib in (("old", old), ("new", new)):
            found = lib.search(q["q"])
            names = [lib.docs[f["doc"]]["file"] for f in found]
            best = max(found, key=lambda f: f["cos"])
            r[side] = {"best": best["cos"], "para": best["para"], "five": names[:5],
                       "right": [i + 1 for i, n in enumerate(names) if any(n.startswith(x) for x in q.get("right", []))]}
        r["tail"] = r["new"]["para"] in tail
        results.append(r)
    print("\n%-52s %-16s %-16s %s" % ("question", "as one passage", "split", "first five"))
    for r in results:
        o, n = r["old"], r["new"]
        def where(s):
            return "%.3f %s" % (s["best"], ",".join("#%d" % i for i in s["right"][:3]) or "-")
        same = "same" if o["five"] == n["five"] else "%d of 5 shared" % len(set(o["five"]) & set(n["five"]))
        print("%-52s %-16s %-16s %s%s" % ((r["kind"][0] + " " + r["q"])[:52], where(o), where(n), same,
                                          "  (best passage: text never embedded before)" if r["tail"] else ""))
    for side, label in (("old", "as one passage"), ("new", "split")):
        ans = [r[side] for r in results if r["kind"] == "answerable"]
        top = {k: [r[side]["best"] for r in results if r["kind"] == k] for k in ("answerable", "near-miss", "off-topic")}
        print("\n%s: right document first %d/%d, in the first 3 %d/%d; weakest answer %.3f%s"
              % (label, sum(1 in a["right"] for a in ans), len(ans), sum(any(i <= 3 for i in a["right"]) for a in ans),
                 len(ans), min(top["answerable"]), "" if not top["off-topic"] else ", strongest off-topic %.3f, strongest "
                 "near-miss %.3f" % (max(top["off-topic"]), max(top["near-miss"]))))
    d = [r["new"]["best"] - r["old"]["best"] for r in results]
    print("\nbest score: up for %d questions, down for %d, average %+.4f, at most %+.4f; the first five identical for %d of %d"
          % (sum(x > 1e-6 for x in d), sum(x < -1e-6 for x in d), sum(d) / len(d), max(d, key=abs),
             sum(r["old"]["five"] == r["new"]["five"] for r in results), len(results)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
