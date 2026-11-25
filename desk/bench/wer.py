"""Word error rate: how many words of what was really said the transcript got wrong, missed or
added, as a share of what was said. Case, punctuation and apostrophes don't count; accents do.

    python3 bench/wer.py said.txt heard.txt    → 12% (6 of 50)
"""
import re
import sys
import unicodedata


def words(path):
    text = unicodedata.normalize("NFC", open(path, encoding="utf-8").read().lower())
    return re.findall(r"\w+", text.replace("’", "'").replace("'", " "))


def distance(a, b):
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


said, heard = words(sys.argv[1]), words(sys.argv[2])
wrong = distance(said, heard)
print(f"{100 * wrong / max(1, len(said)):.0f}% ({wrong} of {len(said)})")
