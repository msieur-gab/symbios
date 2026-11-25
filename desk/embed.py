"""embed: a memo or an article → its passages and their meaning as numbers, kept beside it, so the desk can compare
texts (Gab, 2026-10-23: "embed each memo when it arrives, after transcription", and the same "when an article is
shared"). Heavy work like a transcription: one job per document, one at a time, shown in Activity as
"Embedding: <title>" (Gab: "rules apply to all and should follow the exact same pattern").

    ~/Memos/<memo>/.vectors.json          beside the transcript: it goes when the memo's folder goes
    ~/Articles/.vectors/<article>.json    named after the article: removed once the article is gone

The cut: a passage per paragraph, as the writer (or voice.py) made them; a paragraph longer than MiniLM reads
(256 tokens) is cut at its sentence ends into pieces that fit, so none of its text is left unread (35 paragraphs
on the board, 4.7 % of the text, measured 2026-10-23); the title in front of each passage; captions, credits and
reference lists left out (brainboard's rule). MiniLM, all-MiniLM-L6-v2 int8 in ~/.models/compare/all-minilm-l6-v2,
turns each passage into 384 numbers, one passage at a time (in a batch the int8 model rounds a passage by its
neighbours), kept as int8 (brainboard's pack.js). About 0.2 s a passage on the board, a few seconds a memo, 5–15 s
an article, peak under 100 MB (brain: knowledge/retrieval/one-vector-file-per-document-on-orange-pi-zero-2w.md).

What waits is decided by the worker (voice.py) from the files alone: a memo whose transcript is done, or an article,
whose vector file is missing, older than it, or of another recipe (FINGERPRINT). A file is written as a new one
renamed over the old, so a cut power or a stopped job leaves the old file or the new one, never half of one. Only
this file's job loads the model, run as heavy work (voice.capped): the desk server never does.

    python3 embed.py FILE    # a transcript.md or an article: its vector file written, its passages counted
"""
import hashlib
import json
import os
import re
import sys

MODELS = os.environ.get("DESK_MODELS", os.path.expanduser("~/.models"))  # the board's models (board/install.sh)
MODEL = os.path.join(MODELS, "compare", "all-minilm-l6-v2")  # model_quantized.onnx and tokenizer.json
PYTHON = os.path.join(MODELS, "shared", "python")  # onnxruntime and numpy, PyPI's builds for the board
# another model, cut or order: every file is redone. v2 (2026-10-23): long paragraphs cut at sentence ends
FINGERPRINT = "minilm-l6-v2.q8.d384.paragraph.sentences256.title.b1.i8.v2"
DIM, SCALE, LONGEST = 384, 127, 256  # vector size; int8 = round(v * 127); tokens MiniLM reads, [CLS] and [SEP] included
# a paragraph with 3 of these is a reference, not a thought (brainboard's citation rule, nlu-comparison/cleanup.py)
CITE = re.compile(r"(University Press|Journal|Review|\(\d{4}\)|\b(19|20)\d\d\)?[:,]\s*\d+[–-]\d+|“[^”]{10,}”,)")
FOOTNOTE = re.compile(r"^\[?\d{1,3}\.?\]?\s.*\b(19|20)\d\d\b")  # "26. Thomas Patterson, Out of Order (…, 1993)"
SHORT = 8  # words: a paragraph shorter than this is a caption, a credit or a heading
SENTENCE = re.compile(r"(?<=[.?!…])\s+")


def front(text):
    """(front matter as a dict, body) of a markdown file; quoted values read as article.py writes them (JSON)."""
    if not (text.startswith("---\n") and "\n---" in text[4:]):
        return {}, text
    head, body = text[4:].split("\n---", 1)
    card = {}
    for key, value in re.findall(r"^(\w+): ?(.*)$", head, re.M):
        try:
            card[key] = json.loads(value) if value[:1] == '"' else value
        except ValueError:
            card[key] = value.strip('"')
    return card, body


def plain(paragraph):
    """A markdown paragraph as plain text: links kept as their words, images and addresses gone."""
    p = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", paragraph)
    p = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", p)
    p = re.sub(r"https?://\S+", " ", p)
    p = re.sub(r"\\([\\`*_{}\[\]()#+.!|-])", r"\1", p)  # markdown escapes: "1\." is "1."
    p = re.sub(r"(^|\s)[#>*_`|-]+|[*_`]+", " ", p)
    return re.sub(r"\s+", " ", p).strip()


def kept(paragraph):
    return (len(paragraph.split()) >= SHORT and len(CITE.findall(paragraph)) < 3 and not FOOTNOTE.match(paragraph)
            and not paragraph.startswith(("Copyright", "Image Credit", "*(")))


def where(src):
    """(kind, its vector file) of a transcript.md or an article."""
    if os.path.basename(src) == "transcript.md":
        return "memo", os.path.join(os.path.dirname(src), ".vectors.json")
    folder, name = os.path.split(src)
    return "article", os.path.join(folder, ".vectors", os.path.splitext(name)[0] + ".json")


def card(src):
    """(title, link, body, excerpt) of a document, its title as Activity names it."""
    kind = where(src)[0]
    with open(src, encoding="utf-8") as f:
        head, body = front(f.read())
    if kind == "memo":
        body = body.split("\n# ", 1)[-1].split("\n", 1)[-1]  # the heading is the title again
        return head.get("title") or os.path.basename(os.path.dirname(src)), "", body, ""
    return head.get("title") or os.path.splitext(os.path.basename(src))[0], head.get("url", ""), body, head.get("excerpt", "")


def documents(home):
    """Every article, and every memo whose transcript is done: (source, vector file)."""
    out = []
    articles = os.path.join(home, "Articles")
    for f in sorted(os.listdir(articles)) if os.path.isdir(articles) else []:
        if f.endswith(".md") and not f.startswith("."):
            src = os.path.join(articles, f)
            out.append((src, where(src)[1]))
    memos = os.path.join(home, "Memos")
    for d in sorted(os.listdir(memos)) if os.path.isdir(memos) else []:
        src = os.path.join(memos, d, "transcript.md")
        try:
            with open(src, encoding="utf-8") as f:
                done = "\nstatus: done\n" in f.read(800)
        except (OSError, ValueError):  # gone, or not text
            continue
        if done:
            out.append((src, where(src)[1]))
    return out


def fresh(src, dst):
    """Whether a vector file is there, newer than its document, and of this recipe (read from its first bytes)."""
    try:
        if os.path.getmtime(dst) < os.path.getmtime(src):
            return False
        with open(dst, encoding="utf-8") as f:
            return ('"fingerprint": "%s"' % FINGERPRINT) in f.read(200)
    except (OSError, ValueError):
        return False


def waiting(home):
    """The documents to embed: (source, vector file), articles first, then memos, each by name."""
    return [(src, dst) for src, dst in documents(home) if not fresh(src, dst)]


def orphans(home):
    """The article vector files whose article is gone, removed (a memo's goes with its folder). Answers their names."""
    folder, gone = os.path.join(home, "Articles", ".vectors"), []
    for f in os.listdir(folder) if os.path.isdir(folder) else []:
        if f.endswith(".json") and not os.path.exists(os.path.join(home, "Articles", f[:-5] + ".md")):
            os.remove(os.path.join(folder, f))
            gone.append(f)
    return gone


def expect(src):
    """The seconds a document should take, for Activity: about 0.25 s a passage of ~50 words, and the model's load."""
    try:
        words = len(card(src)[2].split())
    except (OSError, ValueError):
        words = 0
    return round(3 + 0.25 * max(1, words // 50))


def passages(tokenizer, title, paragraphs):
    """The passages to embed: each paragraph kept, cut at its sentence ends where it is longer than MiniLM reads."""
    fits = lambda text: len(tokenizer.encode("%s. %s" % (title, text))) <= LONGEST
    out = []
    for p in paragraphs:
        if fits(p):
            out.append(p)
            continue
        cur = ""
        for s in SENTENCE.split(p):
            trial = (cur + " " + s).strip()
            if cur and not fits(trial):
                out.append(cur)
                cur = s
            else:
                cur = trial
        if cur:
            out.append(cur)  # a single sentence longer than MiniLM reads stays whole; its end is cut
    return out


def encoder():
    """MiniLM, loaded: a text → its 384 numbers, of unit length, one text at a time (in a batch the int8 model rounds
    a text by its neighbours). The tokenizer rides along, uncut, for passages(). For the job and for questions (ask.py)."""
    sys.path.insert(0, PYTHON)
    import numpy as np
    import onnxruntime as ort

    import wordpiece

    tok = wordpiece.Tokenizer(os.path.join(MODEL, "tokenizer.json"), 10 ** 9)  # uncut: passages() measures with it
    so = ort.SessionOptions()
    so.intra_op_num_threads = 2  # the board's job limit: 2 of the 4 cores
    sess = ort.InferenceSession(os.path.join(MODEL, "model_quantized.onnx"), so, providers=["CPUExecutionProvider"])
    names = {i.name for i in sess.get_inputs()}

    def vector(text):
        ids = tok.encode(text)
        ids = np.array([ids[:LONGEST - 1] + [tok.sep] if len(ids) > LONGEST else ids], dtype=np.int64)  # MiniLM's limit
        feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.zeros_like(ids)
        v = sess.run(None, feed)[0][0].mean(0)  # mean of the tokens' vectors: one text, no padding to leave out
        return v / max(float(np.linalg.norm(v)), 1e-9)
    vector.tokenizer = tok
    return vector


def embed(src):
    """The document's vector file, written. Answers how many passages it holds. Loads the model: run as heavy work."""
    import base64

    sys.path.insert(0, PYTHON)  # numpy from the board's models, as encoder() (31 Oct: a clean board has no other numpy)
    import numpy as np

    kind, dst = where(src)
    with open(src, encoding="utf-8") as f:
        text = f.read()
    title, url, body, lead = card(src)
    vector = encoder()
    chunks = passages(vector.tokenizer, title, ([lead] if lead else []) + [p for p in (plain(p) for p in re.split(r"\n\s*\n", body)) if kept(p)])
    vecs = np.zeros((0, DIM), np.int8)
    if chunks:
        rows = np.array([vector("%s. %s" % (title, c)) for c in chunks])
        vecs = np.clip(np.round(rows * SCALE), -128, 127).astype(np.int8)
    record = {"fingerprint": FINGERPRINT, "sha": hashlib.sha1(text.encode()).hexdigest(), "kind": kind,
              "file": os.path.basename(os.path.dirname(src) if kind == "memo" else src), "title": title, "url": url,
              "chunks": chunks, "dim": DIM, "vecs64": base64.b64encode(vecs.tobytes()).decode()}  # fingerprint first: fresh() reads it
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst + ".new", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False)
    os.replace(dst + ".new", dst)
    return len(chunks)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print("%d passages" % embed(os.path.abspath(sys.argv[1])))
