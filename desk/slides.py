"""slides: a deck folder in ~/Slides → what the desk shows and what the phone keeps, made once.

A deck is a folder with one PDF. Either the slides themselves (landscape pages, one per slide),
with the speaker notes in a notes.md (one block per slide, split by lines of ---) if there are any;
or the deck exported as notes pages, each page the slide on top and its notes below (Google Slides:
File → Print preview → "1 slide with notes" → Download as PDF). From notes pages, each slide is cut
out of its page and the notes are written to notes.md; a page without a slide holds notes that ran
over, and goes with the slide before it. Everything made goes in a hidden .deck folder:

    .deck/01.jpg …   the slides, 1280 px on the long side, for the screen
    .deck/t01.jpg …  small ones, for the phone's preview of the next slide
    .deck/deck.json  {"title", "count", "size": [w, h], "made": the PDF's time}

It is made again when the PDF changes (notes.md too, when they come from the PDF). The notes are
read from notes.md at each ask, so an edit in the Editor shows at once. pdftoppm comes from Debian (poppler-utils); the rest is the
standard library.

    python3 slides.py FOLDER   # prepare one deck and print what it holds
"""
import fcntl
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from xml.etree import ElementTree as ET

SIZE, THUMB = 1280, 320
DARK = 200  # a grey level under this is ink (0 black, 255 white)
LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"})  # as PDFs write them


def pdf(folder):
    found = sorted(glob.glob(os.path.join(glob.escape(folder), "*.pdf")))
    if not found:
        raise FileNotFoundError("no PDF in this deck")
    return found[0]


def notes_pages(source):
    """Whether a PDF is a deck exported as notes pages, one slide a page: a slide at the top of most of its first four
    pages (quick: the inbox asks). A document with a picture at the top of page 1 is not one (Gab, 24 Nov: "it should
    be 1 slide per page"; his talk's notes, two slides a page, had a slide found on page 1 only and went to Slides)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-f", "1", "-l", "4", "-r", "72", "-gray", source, os.path.join(tmp, "p")],
                       check=True, capture_output=True, timeout=60)
        found = boxes([pgm(os.path.join(tmp, n)) for n in sorted(os.listdir(tmp))])
        return bool(found) and sum(1 for b in found if b) * 2 > len(found)


def render(source):
    """Every page of the PDF as a greyscale picture at 72 dpi, one pixel a point: ((width, height), bytes)."""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-r", "72", "-gray", source, os.path.join(tmp, "p")],
                       check=True, capture_output=True, timeout=600)
        names = sorted(os.listdir(tmp), key=lambda f: int(re.search(r"(\d+)\.pgm$", f).group(1)))
        return [pgm(os.path.join(tmp, f)) for f in names]


def pgm(path):
    """A binary greyscale picture as pdftoppm -gray writes it: (width, height), and its bytes."""
    data = open(path, "rb").read()
    magic, size, depth, px = data.split(b"\n", 3)
    return tuple(map(int, size.split())), px


def boxes(pages):
    """Where the slide sits on each page of a notes-pages PDF, in points: (x0, y0, x1, y1), or None for a
    page with no slide on it. None for the whole PDF when it isn't notes pages (a landscape page in it).
    The page draws a thin frame round the slide: its top edge is the first row, in the top two thirds,
    dark across most of the page's width; its bottom edge the last such row below, within a 4:3 height."""
    out = []
    for (w, h), px in pages:
        if w > h:
            return None
        wide = lambda y: sum(1 for v in px[y * w:(y + 1) * w] if v < DARK) > w * 0.6  # noqa: E731
        top = next((y for y in range(h * 2 // 3) if wide(y)), None)
        if top is None:
            out.append(None)
            continue
        row = px[top * w:(top + 1) * w]
        x0 = next(x for x in range(w) if row[x] < DARK)
        x1 = next(x for x in range(w - 1, -1, -1) if row[x] < DARK)
        bottom = max((y for y in range(top + 1, min(h, top + (x1 - x0) * 3 // 4 + 2)) if wide(y)), default=None)
        if bottom is None or bottom - top < (x1 - x0) // 3:
            bottom = top + round((x1 - x0) * 9 / 16)
        out.append((x0, top, x1, bottom))
    return out if any(out) else None


def page_notes(source, found, pages):
    """The notes of a notes-pages PDF, one per slide: the text under each slide, and all the text of a page
    with no slide (notes that ran over) joined to the slide before it. Slide text hanging off the slide,
    or a box hidden behind the notes, is printed there too; only lines starting at the notes' left edge
    count, words with ink under them, in their line's size. A page number at the foot is left out. Notes pages
    put no space between paragraphs, so they are found again as text reflows: a line that stopped short
    of the right edge, with room left for the next line's first word, ended its paragraph."""
    r = subprocess.run(["pdftotext", "-bbox-layout", source, "-"], check=True, capture_output=True, timeout=600)
    x = "{http://www.w3.org/1999/xhtml}"
    notes, last = [], None  # last: the previous page's last line (its right end, the edge), for a paragraph running over
    for page, box, ((w, h), px) in zip(ET.fromstring(r.stdout).iter(x + "page"), found, pages):
        found_lines = []
        for line in page.iter(x + "line"):
            words = []
            for word in line.iter(x + "word"):
                x0, y0, x1, y1 = (float(word.get(k)) for k in ("xMin", "yMin", "xMax", "yMax"))
                inked = any(v < DARK for y in range(max(0, int(y0)), min(h, int(y1) + 1))
                            for v in px[y * w + max(0, int(x0)):y * w + min(w, int(x1) + 1)])
                if word.text and y0 > (box[3] + 2 if box else 0) and inked:
                    words.append((x0, y0, x1, y1, word.text))
            if words and not (len(words) == 1 and words[0][4].isdigit() and words[0][1] > h * 0.9):
                found_lines.append(words)
        starts = [round(words[0][0]) for words in found_lines]
        edge = max(set(starts), key=starts.count) if starts else 0  # the notes' left edge
        lines = []
        for words in found_lines:
            size = words[0][3] - words[0][1]
            words = [wd for wd in words if abs((wd[3] - wd[1]) - size) <= size * 0.4]
            if abs(words[0][0] - edge) <= 3:
                lines.append((words[0][1], words[0][0], words[-1][2], words[0][2] - words[0][0], " ".join(wd[4] for wd in words)))
        lines.sort()
        right = max((l[2] for l in lines), default=0)
        paragraphs = []
        for i, (y0, x0, x1, first, text) in enumerate(lines):
            ended = i > 0 and lines[i - 1][2] + 6 + first < right  # the line before had room for this word
            if paragraphs and not ended:
                paragraphs[-1] += " " + text
            else:
                paragraphs.append(text)
        if box:
            notes.append(paragraphs)
        elif notes and paragraphs:
            if notes[-1] and last and last[0] + 6 + lines[0][3] >= last[1]:  # the page before ended mid-paragraph
                notes[-1][-1] += " " + paragraphs.pop(0)
            notes[-1] += paragraphs
        if lines:
            last = (lines[-1][2], right)
    return ["\n\n".join(p).translate(LIGATURES) for p in notes]


def cut(source, found, work):
    """Each slide of a notes-pages PDF cut out of its page, inside the frame: 01.jpg … and t01.jpg …
    The frame found at 72 dpi is a point off at most; it is found again on the page drawn at the size the
    slide will be, from outside (its outer edge is sharp against the white page, even round a black slide),
    and the cut starts a line's width (a point) inside it."""
    n = 0
    for page, box in enumerate(found, 1):
        if not box:
            continue
        n += 1
        dpi = SIZE * 72 / (box[2] - box[0] - 1)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", "%.3f" % dpi, "-gray", "-singlefile",
                            source, os.path.join(tmp, "p")], check=True, capture_output=True, timeout=600)
            (w, h), px = pgm(os.path.join(tmp, "p.pgm"))
        k = dpi / 72
        mx, my = round((box[0] + box[2]) / 2 * k), round((box[1] + box[3]) / 2 * k)
        line = max(1, round(k))  # the frame's line, a point wide
        left = next(x for x in range(max(0, round((box[0] - 3) * k)), w) if px[my * w + x] < DARK) + line
        right = next(x for x in range(min(w - 1, round((box[2] + 3) * k)), -1, -1) if px[my * w + x] < DARK) - line
        top = next(y for y in range(max(0, round((box[1] - 3) * k)), h) if px[y * w + mx] < DARK) + line
        bottom = next(y for y in range(min(h - 1, round((box[3] + 3) * k)), -1, -1) if px[y * w + mx] < DARK) - line
        wide, high = right - left + 1, bottom - top + 1
        for prefix, side, quality in (("", SIZE, 88), ("t", THUMB, 75)):
            f = side / wide  # from the page drawn at dpi to this size
            height = round(side * 9 / 16) if abs(high / wide - 9 / 16) < 0.01 else round(high * f)
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", "%.3f" % (dpi * f), "-x", str(round(left * f)),
                            "-y", str(round(top * f)), "-W", str(side), "-H", str(height), "-jpeg", "-jpegopt",
                            "quality=%d" % quality, "-singlefile", source, os.path.join(work, "%s%02d" % (prefix, n))],
                           check=True, capture_output=True, timeout=600)
    return n


def notes(folder, count):
    """The notes from notes.md, one per slide (blocks split by lines of ---), as many as slides."""
    try:
        text = open(os.path.join(folder, "notes.md"), encoding="utf-8").read()
    except FileNotFoundError:
        text = ""
    blocks = [b.strip() for b in re.split(r"(?m)^---\s*$", text)] if text.strip() else []
    return (blocks + [""] * count)[:count]


def ready(folder):
    """Whether the deck's slides are made from its PDF as it is now (deck.json says the PDF's time)."""
    try:
        return json.load(open(os.path.join(folder, ".deck", "deck.json")))["made"] == int(os.path.getmtime(pdf(folder)))
    except (OSError, ValueError, KeyError):
        return False


def prepare(folder):
    """Make the deck's .deck folder if the PDF is newer than it (from notes pages: the slides cut out,
    and their notes written to notes.md), then answer the deck: title, count, size, notes."""
    source = pdf(folder)
    out = os.path.join(folder, ".deck")
    made = int(os.path.getmtime(source))
    # One maker per deck: the inbox may be making it while someone opens it; the second waits, then reads it
    hold = open(os.path.join(folder, ".deck.lock"), "w")
    fcntl.flock(hold, fcntl.LOCK_EX)
    try:
        deck = json.load(open(os.path.join(out, "deck.json")))
        if deck["made"] != made:
            raise ValueError
    except (OSError, ValueError, KeyError):
        work = out + ".making"
        shutil.rmtree(work, ignore_errors=True)
        os.makedirs(work)
        try:
            pages = render(source)
            found = boxes(pages)
            if found:
                count = cut(source, found, work)
                text = "\n\n---\n\n".join(page_notes(source, found, pages)) + "\n"
                with open(os.path.join(folder, "notes.md"), "w", encoding="utf-8") as f:
                    f.write(text)
            for prefix, side, quality in (("", SIZE, 88), ("t", THUMB, 75)) if not found else ():
                subprocess.run(["pdftoppm", "-jpeg", "-jpegopt", "quality=%d" % quality, "-scale-to", str(side),
                                source, os.path.join(work, prefix + "s")], check=True, capture_output=True, timeout=600)
            # pdftoppm numbers pages with as many digits as the last one needs: s1 or s01; named 01.jpg, t01.jpg here
            count = count if found else 0
            for f in sorted(os.listdir(work)):
                m = re.fullmatch(r"(t?)s-0*(\d+)\.jpg", f)
                if m:
                    os.rename(os.path.join(work, f), os.path.join(work, "%s%02d.jpg" % (m.group(1), int(m.group(2)))))
                    count = max(count, int(m.group(2)))
            w, h = jpeg_size(os.path.join(work, "01.jpg"))
            deck = {"title": os.path.basename(os.path.normpath(folder)), "count": count, "size": [w, h], "made": made}
            json.dump(deck, open(os.path.join(work, "deck.json"), "w"))
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise
        shutil.rmtree(out, ignore_errors=True)
        os.rename(work, out)
    finally:
        hold.close()
    return {**deck, "notes": notes(folder, deck["count"])}


def jpeg_size(path):
    """A JPEG's width and height, from its frame header."""
    with open(path, "rb") as f:
        data = f.read(65536)
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1
            continue
        kind, n = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if 0xC0 <= kind <= 0xCF and kind not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7:i + 9], "big"), int.from_bytes(data[i + 5:i + 7], "big")
        i += 2 + n
    return SIZE, SIZE * 9 // 16


def shelf(root):
    """The decks in ~/Slides: every folder holding a PDF, by name."""
    try:
        names = sorted(e.name for e in os.scandir(root) if e.is_dir() and not e.name.startswith("."))
    except FileNotFoundError:
        return []
    return [n for n in names if glob.glob(os.path.join(glob.escape(os.path.join(root, n)), "*.pdf"))]


if __name__ == "__main__":
    print(json.dumps(prepare(sys.argv[1]), indent=1, ensure_ascii=False))
