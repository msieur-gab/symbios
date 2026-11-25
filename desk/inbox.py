"""inbox: what arrives in ~/Inbox goes where the rulebook says, ~/Inbox/rules.md, which Gab edits.

The rulebook is a markdown table, read from the top at each arrival; the first rule that matches wins:

    | from     | kind                 | goes to | then          |
    |----------|----------------------|---------|---------------|
    | recorder | audio                | Memos   | transcribe    |
    | any      | pdf with notes pages | Slides  | make the deck |
    | any      | anything else        | stay    |               |

- from: what the sender says the file is (`?source=` on POST /api/inbox): recorder (the companion's
  voice memos), scan, camera, share, desk (dropped on the desk's page); a file with no word, copied in
  over scp for one, is only matched by `any`.
- kind: audio, video, picture, pdf, "pdf with notes pages" (a deck exported with its speaker notes,
  see slides.py), text, "anything else", or file endings (`.md .txt`). A .webm, .mp4, .ogg or .3gp may
  hold a film or only sound (the phone's memos are .webm): ffprobe looks inside, a picture track makes
  it a video.
- goes to: a folder in the home folder, or `stay` (left in the inbox, for Gab).
- then: transcribe (a memo in that folder, written by voice.py), make the deck (a deck folder in
  that folder, made by slides.py), or nothing. Both are heavy work: one at a time on the board.

A file the rulebook doesn't place stays in the inbox, and is looked at again each round, so a rule
added later takes it. A rulebook line that can't be read is left out, and said in the server's log.
The rulebook is written once, as below, when there is none; after that it is Gab's and is never
rewritten here. Each file's source is kept in Inbox/.received, beside its hash (receive.py).
"""
import os
import re
import shutil
import subprocess
import sys
import threading

import voice

RULES = "rules.md"
STARTER = """# Inbox rules

What arrives in the inbox goes where these rules say. They are read from the top, and the first one
that matches a file wins. Edit them freely: a change counts from the next file.

- **from**: what the sender says the file is: recorder (the phone's voice memos), scan, camera,
  share, desk (dropped on the desk), or any.
- **kind**: audio, video, picture, pdf, pdf with notes pages (a deck exported with its speaker
  notes), text, anything else, or file endings such as `.md .txt`.
- **goes to**: a folder in the home folder, or stay (left here in the inbox).
- **then**: transcribe, make the deck, or nothing.

| from     | kind                 | goes to   | then          |
|----------|----------------------|-----------|---------------|
| recorder | audio                | Memos     | transcribe    |
| any      | video                | Videos    |               |
| any      | audio                | Music     |               |
| scan     | picture              | Documents |               |
| any      | picture              | Pictures  |               |
| any      | pdf with notes pages | Slides    | make the deck |
| any      | pdf                  | Documents |               |
| any      | .md .txt             | Notes     |               |
| any      | anything else        | stay      |               |
"""
EITHER = (".webm", ".mp4", ".ogg", ".3gp", ".mkv", ".mov", ".m4v")  # a film or only sound: looked inside
KINDS = {
    "audio": tuple(e for e in voice.AUDIO if e not in EITHER) + EITHER,
    "video": EITHER + (".avi", ".ogv", ".mpg", ".mpeg"),
    "picture": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".avif", ".bmp", ".tif", ".tiff"),
    "pdf": (".pdf",),
    "text": (".md", ".txt"),
}
THEN = ("", "transcribe", "make the deck")
SOURCES = ("any", "recorder", "scan", "camera", "share", "desk")
SETTLED = 5  # a file copied in (scp) is left until it hasn't changed for this long
ROUTING = threading.Lock()  # one file placed at a time: the server's uploads and the worker's rounds
SAID = set()  # the rulebook lines already said to be left out, so the log says each once


def rules(inbox):
    """The rulebook's rules, in order: (from, kind, goes to, then). Written once if there is none."""
    path = os.path.join(inbox, RULES)
    if not os.path.exists(path):
        os.makedirs(inbox, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(STARTER)
    out = []
    for n, line in enumerate(open(path, encoding="utf-8"), 1):
        cells = [c.strip().strip("`").strip() for c in line.strip().strip("|").split("|")]
        if not line.lstrip().startswith("|") or len(cells) < 3 or set("".join(cells)) <= set("-: "):
            continue
        source, kind, where = (c.lower() for c in cells[:3])
        then = cells[3].lower() if len(cells) > 3 else ""
        then = "" if then.startswith("(") else then  # "(later: OCR)": a note, not a step
        if source == "from":
            continue  # the heading
        problem = (source not in SOURCES and "from: " + source or
                   not kind and "no kind" or
                   then not in THEN and "then: " + then or
                   where != "stay" and (where.startswith((".", "/")) or ".." in where.split("/")) and "goes to: " + where or
                   then == "transcribe" and where != "memos" and "transcribe goes to Memos only" or "")
        if problem:
            if (line, problem) not in SAID:
                SAID.add((line, problem))
                sys.stderr.write("inbox: %s line %d left out (%s)\n" % (path, n, problem))
            continue
        out.append((source, kind, cells[2] if where != "stay" else "stay", then))
    return out


def matches(kind, name, path):
    """Whether a file is of a kind the rulebook names."""
    ext = os.path.splitext(name)[1].lower()
    if kind in ("anything else", "any", "anything"):
        return True
    if kind in ("pdf with notes pages", "pdf with notes"):
        if ext != ".pdf":
            return False
        import slides
        try:
            return slides.notes_pages(path)
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
    if kind in ("audio", "video") and ext in EITHER:
        return (kind == "video") == film(path)
    if kind in KINDS:
        return ext in KINDS[kind]
    endings = kind.replace(",", " ").split()
    return bool(endings) and all(e.startswith(".") for e in endings) and ext in endings


def film(path):
    """Whether a file has a picture track (ffprobe): a film, not only sound. A cover picture in a
    sound file doesn't count."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                              "stream=codec_name:stream_disposition=attached_pic", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return any(line and not line.endswith(",1") for line in out.splitlines())


def place(home, path, source):
    """Put one file from the inbox where the first matching rule says, and start what follows.
    Answers the folder it went to, relative to the home folder ("Inbox" when it stays)."""
    went = settle(home, path, source)
    if went:
        import signals
        signals.publish(went, os.path.basename(path))
    return went


def settle(home, path, source):
    inbox = os.path.join(home, "Inbox")
    name = os.path.basename(path)
    with ROUTING:
        if not os.path.isfile(path):
            return None
        for src, kind, where, then in rules(inbox):
            if src not in ("any", source) or not matches(kind, name, path):
                continue
            if where == "stay":
                return "Inbox"
            folder = os.path.join(home, where)
            if then == "transcribe":
                return os.path.relpath(voice.adopt(path, folder), home)
            if then == "make the deck":
                return os.path.relpath(new_deck(path, folder), home)
            os.makedirs(folder, exist_ok=True)
            os.replace(path, free(os.path.join(folder, name)))
            return where
        return "Inbox"


def new_deck(path, folder, name=None):
    """A deck's PDF into a folder of its own in `folder` (Slides), named after it, and its slides made: from the inbox
    and from a drop on the desk (place.py), which gives the name it cleaned. Answers the deck's folder."""
    name = name or os.path.basename(path)
    title = os.path.splitext(name)[0]
    if os.path.splitext(title)[1].lower() in (".pptx", ".ppt", ".key", ".odp"):
        title = os.path.splitext(title)[0]  # "Pitch.pptx.pdf", as some exports name it: the deck is "Pitch"
    deck = free(os.path.join(folder, title))
    os.makedirs(deck)
    shutil.move(path, os.path.join(deck, name))
    threading.Thread(target=make_deck, args=(deck,), daemon=True).start()
    return deck


def free(path):
    """path, or path with (2), (3)… before its ending when something is there already."""
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        n += 1
        path = "%s (%d)%s" % (stem, n, ext)
    return path


MAKING = set()  # the deck folders being made, or waiting for their turn
FAILED = {}  # deck folder → its PDF's time, when making it failed: not tried again until the PDF changes


def make_deck(folder):
    """The deck's slides and notes, made now, as heavy work: capped like a transcription (2 cores, lowest
    priority, slowed above 600 MB), and one heavy job at a time on the board. Every deck is made this way."""
    import signals
    with ROUTING:
        if folder in MAKING:
            return
        MAKING.add(folder)
    id, name = "deck:" + folder, "Making the deck: " + os.path.basename(folder)  # the work first, as every line (Gab, 2026-10-23)
    signals.task(id, name, "pending", "deck")
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with voice.HEAVY:
            signals.task(id, name, "running", "deck", expect=pages(folder) * 2.0 + 4)  # about 1.8 s a page on the board
            r = subprocess.run(voice.capped([sys.executable, os.path.join(here, "slides.py"), folder]), capture_output=True,
                               text=True, timeout=1900)
        if r.returncode:
            sys.stderr.write("inbox: the deck in %s wasn't made: %s\n" % (folder, (r.stderr.strip().splitlines() or ["?"])[-1]))
            FAILED[folder] = pdf_time(folder)
        signals.task(id, name, "failed" if r.returncode else "done")
        signals.publish(os.path.relpath(folder, os.path.dirname(os.path.dirname(folder))), "")
    finally:
        MAKING.discard(folder)


def pages(folder):
    """How many pages the deck's PDF has (pdfinfo), for Activity's time left; 20 when it can't tell."""
    import slides
    try:
        out = subprocess.run(["pdfinfo", slides.pdf(folder)], capture_output=True, text=True, timeout=20).stdout
        return int(re.search(r"^Pages:\s+(\d+)", out, re.M).group(1))
    except (OSError, AttributeError, subprocess.SubprocessError):
        return 20


def deck_ready(folder):
    """Whether a deck can be shown: its slides made from its PDF as it is now. If not, they are being made
    (started here when nothing is making them yet), and the deck can't be opened until they are."""
    import slides
    if folder not in MAKING and slides.ready(folder):
        return True
    if folder not in MAKING and FAILED.get(folder) != pdf_time(folder):
        threading.Thread(target=make_deck, args=(folder,), daemon=True).start()
    return False


def pdf_time(folder):
    import slides
    try:
        return os.path.getmtime(slides.pdf(folder))
    except (OSError, FileNotFoundError):
        return None


def sources(inbox):
    """The source each file came with, from Inbox/.received: {name in the inbox: source}."""
    out = {}
    try:
        for line in open(os.path.join(inbox, ".received"), encoding="utf-8"):
            cells = line.rstrip("\n").split("\t")
            if len(cells) > 3:
                out[os.path.basename(cells[2])] = cells[3]
    except FileNotFoundError:
        pass
    return out


def sweep(home):
    """Place what waits in the inbox: files copied in some other way, and those a rule left there before.
    A file still arriving, hidden, or the rulebook itself is left alone."""
    import time
    inbox = os.path.join(home, "Inbox")
    if not os.path.isdir(inbox):
        return
    said = None
    for name in sorted(os.listdir(inbox)):
        path = os.path.join(inbox, name)
        if name.startswith(".") or name == RULES or not os.path.isfile(path):
            continue
        if time.time() - os.stat(path).st_ctime < SETTLED and time.time() - os.path.getmtime(path) < SETTLED:
            continue
        said = said if said is not None else sources(inbox)
        place(home, path, said.get(name, "any"))
