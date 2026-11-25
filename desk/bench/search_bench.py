"""Search the board's own content by meaning and by keyword, and say "not here" when nothing matches.

A test bench, not the desk: it reads ~/Articles and ~/Memos and writes only into its own folder.
Gab, 2026-10-23: "search via keywords or questions if any of the board content contains something about
a given topic … return a list of links to the different matching article above a certain threshold and
abstain when nothing is matching".

The recipe is brainboard's, measured on Gab's library in September and October (brain:
knowledge/retrieval/librarian-verdict-management-over-model.md, small-colbert-vs-minilm.md):
  - all-MiniLM-L6-v2 int8 (brainboard's vendored copy), mean pooling, L2-normalised
  - one passage per paragraph, embedded as "<title>. <paragraph>"; bibliography paragraphs dropped
  - an article's score is its best paragraph's cosine; the floor decides "not here"
  - keywords: SQLite FTS5 (BM25) on the same paragraphs, fused with the meaning by rank (1/(60+rank))

    python3 search_bench.py index HOME OUT            # embed every paragraph → OUT/{chunks.json,vecs.npy,fts.sqlite}
    python3 search_bench.py ask OUT "question" [FLOOR] # the articles that match, best first, or "not here"
    python3 search_bench.py eval OUT questions.json    # every question: scores, where the right articles land

MODEL (env) is the folder with tokenizer.json and model_quantized.onnx (default: ~/.models/compare/all-minilm-l6-v2, where
board/install.sh puts it; onnxruntime and numpy are in ~/.models/shared/python, for PYTHONPATH).
"""
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np
import onnxruntime as ort

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # the desk's folder (or this one, copied beside it)
import wordpiece  # MiniLM's tokenizer in plain Python: no `tokenizers` package on the board

MODEL = os.environ.get("MODEL", os.path.expanduser("~/.models/compare/all-minilm-l6-v2"))
# brainboard's citation rule (nlu-comparison/cleanup.py): a paragraph with 3+ markers is a reference
CITE = re.compile(r"(University Press|Journal|Review|\(\d{4}\)|\b(19|20)\d\d\)?[:,]\s*\d+[–-]\d+|“[^”]{10,}”,)")
FOOTNOTE = re.compile(r"^\[?\d{1,3}\.?\]?\s.*\b(19|20)\d\d\b")  # "26. Thomas Patterson, Out of Order (…, 1993)"
SHORT = 8  # words: a paragraph shorter than this is a caption, a credit or a heading
STOP = set("a an the and or but of to for in on at by from with is are was were be been do does did how what "
           "which who whom why when where can could should would will i my me you your we our it its this that "
           "there their about any some as if not no".split())


def front(text):
    """(front matter as a dict, body) of a markdown file."""
    if text.startswith("---\n") and "\n---" in text[4:]:
        head, body = text[4:].split("\n---", 1)
        return dict(re.findall(r"^(\w+): ?\"?(.*?)\"?$", head, re.M)), body
    return {}, text


def plain(paragraph):
    """A markdown paragraph as plain text: links kept as their words, images and URLs gone."""
    p = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", paragraph)
    p = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", p)
    p = re.sub(r"https?://\S+", " ", p)
    p = re.sub(r"\\([\\`*_{}\[\]()#+.!|-])", r"\1", p)  # markdown escapes: "1\." is "1."
    p = re.sub(r"(^|\s)[#>*_`|-]+|[*_`]+", " ", p)
    return re.sub(r"\s+", " ", p).strip()


def documents(home):
    """Every article and memo: {kind, file, title, paragraphs}."""
    out = []
    articles = os.path.join(home, "Articles")
    for f in sorted(os.listdir(articles)) if os.path.isdir(articles) else []:
        if f.endswith(".md"):
            card, body = front(open(os.path.join(articles, f), encoding="utf-8").read())
            out.append({"kind": "article", "file": f, "title": card.get("title") or f[:-3], "lead": card.get("excerpt", ""),
                        "paragraphs": [plain(p) for p in re.split(r"\n\s*\n", body)]})
    memos = os.path.join(home, "Memos")
    for d in sorted(os.listdir(memos)) if os.path.isdir(memos) else []:
        path = os.path.join(memos, d, "transcript.md")
        if os.path.isfile(path):
            card, body = front(open(path, encoding="utf-8").read())
            body = body.split("\n# ", 1)[-1].split("\n", 1)[-1]  # the heading is the title again
            out.append({"kind": "memo", "file": d, "title": card.get("title") or d, "lead": "",
                        "paragraphs": [plain(p) for p in re.split(r"\n\s*\n", body)]})
    return out


def kept(paragraph):
    return (len(paragraph.split()) >= SHORT and len(CITE.findall(paragraph)) < 3 and not FOOTNOTE.match(paragraph)
            and not paragraph.startswith(("Copyright", "Image Credit", "*(")))


def encoder():
    tok = wordpiece.Tokenizer(os.path.join(MODEL, "tokenizer.json"), 256)  # longer text is cut
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2  # the board's job limit: 2 of the 4 cores
    sess = ort.InferenceSession(os.path.join(MODEL, "model_quantized.onnx"), so, providers=["CPUExecutionProvider"])
    names = {i.name for i in sess.get_inputs()}

    def embed(texts, batch=8):
        out = []
        for s in range(0, len(texts), batch):
            seqs = [tok.encode(t) for t in texts[s:s + batch]]
            width = max(len(q) for q in seqs)  # padded to the batch's longest
            ids = np.array([q + [0] * (width - len(q)) for q in seqs], dtype=np.int64)
            mask = np.array([[1] * len(q) + [0] * (width - len(q)) for q in seqs], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in names:
                feed["token_type_ids"] = np.zeros_like(ids)
            h = sess.run(None, feed)[0]
            m = mask[..., None].astype(np.float32)
            v = (h * m).sum(1) / np.clip(m.sum(1), 1e-9, None)
            out.append(v / np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-9, None))
        return np.concatenate(out).astype(np.float32) if out else np.zeros((0, 384), np.float32)
    return embed


def index(home, out):
    t0 = time.time()
    docs = documents(home)
    chunks = []
    for di, d in enumerate(docs):
        if d["lead"]:
            chunks.append({"doc": di, "text": d["lead"]})
        chunks += [{"doc": di, "text": p} for p in d["paragraphs"] if kept(p)]
    embed = encoder()
    t1 = time.time()
    vecs = embed(["%s. %s" % (docs[c["doc"]]["title"], c["text"]) for c in chunks])
    t2 = time.time()
    os.makedirs(out, exist_ok=True)
    np.save(os.path.join(out, "vecs.npy"), vecs)
    for d in docs:
        del d["paragraphs"]
    json.dump({"docs": docs, "chunks": chunks}, open(os.path.join(out, "chunks.json"), "w", encoding="utf-8"), ensure_ascii=False)
    if os.path.exists(os.path.join(out, "fts.sqlite")):
        os.remove(os.path.join(out, "fts.sqlite"))
    db = sqlite3.connect(os.path.join(out, "fts.sqlite"))
    db.execute("create virtual table p using fts5(title, text, tokenize='porter unicode61')")
    db.executemany("insert into p(rowid, title, text) values (?, ?, ?)",
                   [(i, docs[c["doc"]]["title"], c["text"]) for i, c in enumerate(chunks)])
    db.commit()
    print("%d documents (%d articles, %d memos), %d paragraphs; loading %.1f s, embedding %.1f s (%.0f ms a paragraph), all %.1f s"
          % (len(docs), sum(d["kind"] == "article" for d in docs), sum(d["kind"] == "memo" for d in docs), len(chunks),
             t1 - t0, t2 - t1, 1000 * (t2 - t1) / max(len(chunks), 1), time.time() - t0))


class Library:
    def __init__(self, out):
        data = json.load(open(os.path.join(out, "chunks.json"), encoding="utf-8"))
        self.docs, self.chunks = data["docs"], data["chunks"]
        self.vecs = np.load(os.path.join(out, "vecs.npy"))
        self.of = np.array([c["doc"] for c in self.chunks])
        self.db = sqlite3.connect(os.path.join(out, "fts.sqlite"))
        self.embed = encoder()

    def search(self, question):
        """Every document with its best paragraph by meaning (cosine), its keyword rank, and the fused order."""
        cos = self.vecs @ self.embed([question])[0]
        best = {}
        for i in np.argsort(-cos):
            best.setdefault(int(self.of[i]), (float(cos[i]), int(i)))
        meaning = sorted(best, key=lambda d: -best[d][0])
        words = [w for w in re.findall(r"[\w.]+", question.lower()) if w.strip(".") and w not in STOP]
        keyword = []
        if words:
            q = " OR ".join('"%s"' % w.strip(".").replace('"', "") for w in words)
            for (rowid,) in self.db.execute("select rowid from p where p match ? order by bm25(p, 2.0, 1.0) limit 200", (q,)):
                d = int(self.of[rowid])
                if d not in keyword:
                    keyword.append(d)
        fused = {d: 1 / (60 + meaning.index(d) + 1) + (1 / (60 + keyword.index(d) + 1) if d in keyword else 0) for d in best}
        order = sorted(best, key=lambda d: -fused[d])
        return [{"doc": d, "cos": best[d][0], "para": best[d][1], "kw": keyword.index(d) + 1 if d in keyword else None,
                 "meaning": meaning.index(d) + 1} for d in order]


def ask(out, question, floor=None):
    t0 = time.time()
    lib = Library(out)
    t1 = time.time()
    found = lib.search(question)
    t2 = time.time()
    floor = float(floor) if floor is not None else None
    shown = [f for f in found if floor is None or f["cos"] >= floor][:5]
    print("loading %.2f s, question %.2f s" % (t1 - t0, t2 - t1))
    if not shown:
        print("not here: nothing in the articles or memos is about this (best %.3f, floor %.3f)" % (max(f["cos"] for f in found), floor))
    for f in shown:
        d = lib.docs[f["doc"]]
        print("%.3f  %-7s %s  (meaning #%d, keywords %s)\n        %s…"
              % (f["cos"], d["kind"], d["title"][:70], f["meaning"], "#%d" % f["kw"] if f["kw"] else "-",
                 lib.chunks[f["para"]]["text"][:150]))


def evaluate(out, questions):
    lib = Library(out)
    qs = json.load(open(questions, encoding="utf-8"))["questions"]
    rows = []
    t0 = time.time()
    for q in qs:
        found = lib.search(q["q"])
        names = [lib.docs[f["doc"]]["file"] for f in found]
        right = [i + 1 for i, n in enumerate(names) if any(n.startswith(r) for r in q.get("right", []))]
        rows.append({**q, "best": max(f["cos"] for f in found), "top": names[0], "right_at": right,  # what the floor is held against
                     "right_cos": [found[i - 1]["cos"] for i in right]})
    took = (time.time() - t0) / len(qs)
    for kind in ("answerable", "near-miss", "off-topic"):
        print("\n== %s" % kind)
        for r in (r for r in rows if r["kind"] == kind):
            where = " ".join("#%d %.3f" % (i, c) for i, c in zip(r["right_at"], r["right_cos"])) if r["right_at"] else ""
            print("%.3f  %-58s %s%s" % (r["best"], r["q"][:58], where, "" if r["right_at"] or kind != "answerable" else "MISSING"))
    best = {k: [r["best"] for r in rows if r["kind"] == k] for k in ("answerable", "near-miss", "off-topic")}
    floor, sure = max(best["off-topic"]) + 0.005, max(best["near-miss"]) + 0.005
    ans = [r for r in rows if r["kind"] == "answerable"]
    print("\n%.2f s a question (search only, model loaded)" % took)
    print("right article first: %d/%d, in the first 3: %d/%d"
          % (sum(1 in r["right_at"] for r in ans), len(ans), sum(any(i <= 3 for i in r["right_at"]) for r in ans), len(ans)))
    print("floor (just above every off-topic question) %.3f: answerable above it %d/%d"
          % (floor, sum(r["best"] >= floor for r in ans), len(ans)))
    print("'sure' (just above every near-miss) %.3f: answerable above it %d/%d"
          % (sure, sum(r["best"] >= sure for r in ans), len(ans)))
    print("gap: weakest answerable %.3f, strongest off-topic %.3f, strongest near-miss %.3f"
          % (min(best["answerable"]), max(best["off-topic"]), max(best["near-miss"])))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "index":
        index(sys.argv[2], sys.argv[3])
    elif cmd == "ask":
        ask(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    elif cmd == "eval":
        evaluate(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
