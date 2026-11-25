"""MiniLM's tokenizer in plain Python, so the board needs no `tokenizers` package (11 MB) for search (Gab, 2026-10-23:
"yes do all 3"). It reads the model's own tokenizer.json and does what that file asks: BERT's normaliser (control
characters out, Chinese characters spaced, accents stripped, lowercase), split on spaces and punctuation, then
WordPiece, longest piece first, "##" before a word's continuation, [UNK] for a word it can't cut.

Checked on the laptop on 23 Oct 2026: the same ids as `tokenizers` for all 1,056 texts (every passage of the board's
articles and memos, the questions, accents, Chinese, emoji, a 150-letter word). One difference, on purpose: "[CLS]"
written in a passage stays text here; `tokenizers` turns it into the model's own marker.

    python3 wordpiece.py check MODEL HOME [questions.json]   # the same token ids as `tokenizers`, on every passage?
"""
import json
import os
import sys
import unicodedata


class Tokenizer:
    def __init__(self, path, longest=256):
        t = json.load(open(path, encoding="utf-8"))
        self.vocab = t["model"]["vocab"]
        self.unk, self.most = self.vocab[t["model"]["unk_token"]], t["model"]["max_input_chars_per_word"]
        self.prefix = t["model"]["continuing_subword_prefix"]
        self.cls, self.sep = self.vocab["[CLS]"], self.vocab["[SEP]"]
        self.longest = longest  # [CLS] and [SEP] included, as tokenizers' truncation counts them

    @staticmethod
    def normal(text):
        out = []
        for c in text:
            o = ord(c)
            if o == 0 or o == 0xFFFD or (unicodedata.category(c) in ("Cc", "Cf") and c not in "\t\n\r"):
                continue
            if c in " \t\n\r" or unicodedata.category(c) == "Zs":
                out.append(" ")
            elif (0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2A6DF or 0x2A700 <= o <= 0x2B73F
                  or 0x2B740 <= o <= 0x2B81F or 0x2B820 <= o <= 0x2CEAF or 0xF900 <= o <= 0xFAFF or 0x2F800 <= o <= 0x2FA1F):
                out.append(" %s " % c)
            else:
                out.append(c)
        text = unicodedata.normalize("NFD", "".join(out))
        return "".join(c for c in text if unicodedata.category(c) != "Mn").lower()

    @staticmethod
    def punct(c):
        o = ord(c)
        return 33 <= o <= 47 or 58 <= o <= 64 or 91 <= o <= 96 or 123 <= o <= 126 or unicodedata.category(c).startswith("P")

    def words(self, text):
        out, word = [], ""
        for c in self.normal(text):
            if c.isspace():
                out, word = out + ([word] if word else []), ""
            elif self.punct(c):
                out, word = out + ([word] if word else []) + [c], ""
            else:
                word += c
        return out + ([word] if word else [])

    def pieces(self, word):
        if len(word) > self.most:
            return [self.unk]
        out, start = [], 0
        while start < len(word):
            end = len(word)
            while end > start:
                piece = (self.prefix if start else "") + word[start:end]
                if piece in self.vocab:
                    out.append(self.vocab[piece])
                    break
                end -= 1
            if end == start:
                return [self.unk]
            start = end
        return out

    def encode(self, text):
        """Token ids with [CLS] and [SEP], cut to `longest`."""
        ids = []
        for w in self.words(text):
            ids += self.pieces(w)
            if len(ids) >= self.longest - 2:
                break
        return [self.cls] + ids[:self.longest - 2] + [self.sep]


def check(model, home, questions=None):
    """Every passage search_bench embeds, its title in front, and every question: the same ids as `tokenizers`?"""
    from tokenizers import Tokenizer as Rust
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench"))
    import search_bench
    rust = Rust.from_file(os.path.join(model, "tokenizer.json"))
    rust.enable_truncation(max_length=256)
    rust.no_padding()  # search_bench pads each batch to its longest itself
    mine = Tokenizer(os.path.join(model, "tokenizer.json"))
    texts = []
    for d in search_bench.documents(home):
        texts += ["%s. %s" % (d["title"], p) for p in [d["lead"]] + d["paragraphs"] if p]
    if questions:
        texts += [q["q"] for q in json.load(open(questions, encoding="utf-8"))["questions"]]
    texts += ["Café naïve résumé — “quotes” … 3,5 % ½ ① emoji 🙂 tab\there", "中文字符 and 日本語", "x" * 150,
              "supercalifragilisticexpialidocious", "[CLS] brackets [SEP]", "a​zero width\u0007bell"]
    bad = [t for t in texts if rust.encode(t).ids != mine.encode(t)]
    print("%d texts, %d tokens; %d differ" % (len(texts), sum(len(mine.encode(t)) for t in texts), len(bad)))
    for t in bad[:5]:
        r, m = rust.encode(t).ids, mine.encode(t)
        i = next((i for i, (a, b) in enumerate(zip(r, m)) if a != b), min(len(r), len(m)))
        print("  %r\n    tokenizers %s\n    plain      %s" % (t[:80], r[max(0, i - 3):i + 4], m[max(0, i - 3):i + 4]))


if __name__ == "__main__":
    if len(sys.argv) > 3 and sys.argv[1] == "check":
        check(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    else:
        print(__doc__)
