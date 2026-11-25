"""place: where something dropped on the desk goes, by the inbox's rulebook (~/Inbox/rules.md, Gab's to edit).

The rulebook is the desk's (desk/inbox.py), read the same way: a markdown table, read from the top, the
first rule that matches wins. Here it places what is dropped on the desk:

- a file, by its kind (audio, video, picture, pdf, text, or file endings);
- a folder, whole, by the kind most of its files have, so an album keeps its cover beside its tracks
  (Gab's drop-anywhere prototype, ~/dev/file-system);
- a .zip, opened first, then placed as the folder it holds;
- music goes into its artist's folder: an album to Music/<artist>/<album>, a loose track to
  Music/<artist>/<album>/, from the tags in the sound (album artist, else artist; tags.py, ffprobe for the rare others). An artist's
  folder already there is used, whatever its capitals. Without tags, music stays where the rule sends it.
  (Gab, 23 Nov: "if it's not going to the artist folder, then I will call it a failure".)

What no rule places stays in ~/Inbox. A name already taken gets " (2)", " (3)"… The rulebook is the inbox's own
(its starter, its reading): a deck exported as notes pages goes to Slides, in a folder of its own, and its slides are
made, as from the phone (Gab, 24 Nov: a deck dropped on the Lyra went to Documents). Transcribing stays the phone's.

Standard library only; ffprobe, when there, tells a film from a sound in a .webm or .mp4.
"""
import json
import os
import shutil
import subprocess
import sys
import zipfile

from inbox import rules, matches as inbox_matches, new_deck
from tags import read as read_tags

EITHER = (".webm", ".mp4", ".ogg", ".3gp", ".mkv", ".mov", ".m4v")  # a film or only sound: looked inside
KINDS = {
    "audio": (".mp3", ".m4a", ".aac", ".oga", ".opus", ".flac", ".wav", ".wma") + EITHER,
    "video": EITHER + (".avi", ".ogv", ".mpg", ".mpeg", ".wmv"),
    "picture": (".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif", ".avif", ".bmp", ".tif", ".tiff"),
    "pdf": (".pdf",),
    "text": (".md", ".txt"),
}
SOURCES = ("any", "recorder", "scan", "camera", "share", "desk")
SKIP = (".DS_Store", "Thumbs.db", "desktop.ini")
ZIP_LIMIT = 4 * 1024 ** 3  # what a zip may unpack to, at most: a zip that says more is not opened


def film(path):
    """Whether a file has a picture track (ffprobe): a film, not only sound. A cover picture doesn't count."""
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries",
                              "stream=codec_name:stream_disposition=attached_pic", "-of", "csv=p=0", path],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return os.path.splitext(path)[1].lower() in (".mp4", ".mkv", ".mov", ".m4v")
    return any(line and not line.endswith(",1") for line in out.splitlines())


def matches(kind, path):
    """Whether a file is of a kind the rulebook names."""
    ext = os.path.splitext(path)[1].lower()
    if kind in ("anything else", "any", "anything"):
        return True
    if kind in ("pdf with notes pages", "pdf with notes"):  # a deck: the inbox looks at its pages (slides.py)
        return inbox_matches(kind, os.path.basename(path), path)
    if kind in ("audio", "video") and ext in EITHER:
        return (kind == "video") == film(path)
    if kind in KINDS:
        return ext in KINDS[kind]
    endings = kind.replace(",", " ").split()
    return bool(endings) and all(e.startswith(".") for e in endings) and ext in endings


def kind_of(path):
    """A file's kind in the rulebook's words, or None."""
    for kind in ("audio", "video", "picture", "pdf", "text"):
        if matches(kind, path):
            return kind
    return None


def destination(home, path, source="desk"):
    """Where the first matching rule sends this file, a folder relative to the home or "Inbox", and what follows."""
    for src, kind, where, then in rules(os.path.join(home, "Inbox")):
        if src in ("any", source) and matches(kind, path):
            return ("Inbox", "") if where == "stay" else (where, then)
    return "Inbox", ""


def majority(folder):
    """One file standing for a folder: one of the kind most of its files have (the first file if none has a kind)."""
    counts, first, example = {}, None, {}
    for root, dirs, names in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in names:
            if name.startswith(".") or name in SKIP:
                continue
            path = os.path.join(root, name)
            first = first or path
            kind = kind_of(path)
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
                example.setdefault(kind, path)
    return example[max(counts, key=counts.get)] if counts else first


def free(path):
    """path, or path with (2), (3)… before its ending when something is there already."""
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        n += 1
        path = "%s (%d)%s" % (stem, n, ext)
    return path


def unzip(path, into):
    """A zip's files into the folder `into`; names that climb out, absolute names and macOS litter are left out.
    Answers the names left out. Refuses (ValueError) a zip that would unpack to more than ZIP_LIMIT."""
    left = []
    with zipfile.ZipFile(path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        if sum(m.file_size for m in members) > ZIP_LIMIT:
            raise ValueError("unpacks to more than %d GB" % (ZIP_LIMIT // 1024 ** 3))
        for m in members:
            name = m.filename.replace("\\", "/").lstrip("/")
            parts = name.split("/")
            # hidden names too: a zip dropped on the desk brings no .ssh, .bashrc or .config (review of 24 Nov, C1)
            if not name or ".." in parts or parts[0] == "__MACOSX" or parts[-1] in SKIP or any(p.startswith(".") for p in parts):
                left.append(m.filename)
                continue
            target = os.path.join(into, *parts)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(m) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
    # a zip that holds one folder is that folder
    inside = [e for e in os.listdir(into) if not e.startswith(".")]
    if len(inside) == 1 and os.path.isdir(os.path.join(into, inside[0])):
        return left, os.path.join(into, inside[0])
    return left, into


def tags(path):
    """A sound's {"artist", "album"}, the album artist first: from the file (tags.py), else ffprobe; {} without
    tags. Kept for the drop's length of time, since filing one album asks it several times."""
    key = (path, os.path.getmtime(path) if os.path.exists(path) else 0)
    if key not in TAGS:
        t = read_tags(path)
        if t is None:
            try:
                out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags=album_artist,artist,album",
                                      "-of", "json", path], capture_output=True, text=True, timeout=20).stdout
                t = {k.lower(): v.strip() for k, v in json.loads(out or "{}").get("format", {}).get("tags", {}).items()}
            except (OSError, subprocess.SubprocessError, ValueError):
                t = {}
        artist = t.get("album_artist") or t.get("artist") or ""
        if len(TAGS) > 256:
            TAGS.clear()
        TAGS[key] = {"artist": safe(artist), "album": safe(t.get("album") or "")}
    return TAGS[key]


TAGS = {}


def safe(name):
    """A tag made fit for a folder's name: no slashes, nothing unprintable, no leading dot or space in any mix, not too
    long. Dots were stripped before spaces until 24 Nov, so ". .." became ".." and an album went into the home itself
    (symbios SECURITY.md, review of 24 Nov, C1)."""
    name = "".join(c for c in name if c.isprintable())
    name = " ".join(name.replace("/", "-").replace("\\", "-").split()).lstrip(". ").strip()
    return name[:120]


def within(root, path):
    """Whether path is strictly inside root, symlinks followed."""
    root, path = os.path.realpath(root), os.path.realpath(path)
    return path != root and path.startswith(root + os.sep)


def existing(folder, name):
    """The folder in `folder` called `name`, whatever its capitals, or `name` itself when there is none."""
    try:
        for e in os.listdir(folder):
            if e.lower() == name.lower() and os.path.isdir(os.path.join(folder, e)):
                return e
    except OSError:
        pass
    return name


def by_artist(folder, path, stand):
    """Where music goes inside the music folder: <artist>/ for an album, <artist>/<album>/ for a track. None
    when the sound has no artist tag (it stays where the rule put it)."""
    if not stand or kind_of(stand) != "audio":
        return None
    t = tags(stand)
    if not t.get("artist"):
        return None
    artist = os.path.join(folder, existing(folder, t["artist"]))
    if os.path.isdir(path):
        return artist
    return os.path.join(artist, existing(artist, t["album"])) if t.get("album") else artist


def artist_folder(path, stand):
    """Whether a dropped folder is an artist's: its sounds are in folders inside it (albums), none at its top,
    or its name is the artist's. Then it joins the artist's folder in Music, not a folder inside it."""
    if not os.path.isdir(path) or not stand:
        return False
    top = [e for e in os.listdir(path) if not e.startswith(".")]
    loose = any(e.lower().endswith(KINDS["audio"]) for e in top if os.path.isfile(os.path.join(path, e)))
    artist = tags(stand).get("artist", "")
    return (not loose and any(os.path.isdir(os.path.join(path, e)) for e in top)) or (artist and artist.lower() == os.path.basename(path).lower())


def settle(home, path, source="desk"):
    """Put one dropped thing (a file, a folder, a zip) where the rulebook says.
    Answers {"name", "went": folder relative to home, "path": where it is now, "left": names left out}."""
    name = os.path.basename(path)
    left = []
    if os.path.isfile(path) and name.lower().endswith(".zip"):
        opened = path + ".open"
        os.makedirs(opened)
        try:
            left, inner = unzip(path, opened)
        except (zipfile.BadZipFile, ValueError, OSError) as e:
            shutil.rmtree(opened, ignore_errors=True)
            left = [name + ": " + str(e)]
            inner = None
        if inner:
            whole = os.path.join(os.path.dirname(path), os.path.basename(inner) if inner != opened else name[:-4])
            whole = free(whole)
            os.replace(inner, whole)
            shutil.rmtree(opened, ignore_errors=True)
            os.remove(path)
            path, name = whole, os.path.basename(whole)
    stand = majority(path) if os.path.isdir(path) else path
    went, then = destination(home, stand, source) if stand else ("Inbox", "")
    folder = os.path.join(home, went)
    if went.split("/")[0].lower() == "music":
        if artist_folder(path, stand):  # a folder of an artist's albums: it is the artist's folder itself
            name = existing(folder, tags(stand).get("artist") or name)
        else:
            folder = by_artist(folder, path, stand) or folder
    # what arrives lands inside the folder the rulebook named (Music/…, Documents/…), never above it, never hidden; a
    # name or a tag that would lead elsewhere sends it to the Inbox (review of 24 Nov, C1)
    name = "".join(c for c in name if c.isprintable()).lstrip(". ") or "dropped"
    inside = os.path.join(folder, name)
    if not within(home, os.path.join(home, went.split("/")[0])) or not within(os.path.join(home, went.split("/")[0]), inside):
        sys.stderr.write("place: %r would have gone to %s: kept in the Inbox\n" % (os.path.basename(path), inside))
        folder = os.path.join(home, "Inbox")
        inside = os.path.join(folder, name)
    os.makedirs(folder, exist_ok=True)
    if then == "make the deck" and os.path.isfile(path) and folder != os.path.join(home, "Inbox"):  # a deck: a folder of its own, its slides made
        deck = new_deck(path, folder, name)
        return {"name": name, "went": os.path.relpath(deck, home), "path": os.path.relpath(os.path.join(deck, name), home), "left": left}
    if os.path.isdir(path) and os.path.isdir(inside):  # the same album again: what is new joins it
        merge(path, inside)
        target = inside
    else:
        target = free(inside)
        shutil.move(path, target)
    return {"name": name, "went": os.path.relpath(folder, home), "path": os.path.relpath(target, home), "left": left}


def merge(src, dst):
    """A folder into one of the same name: its new files join; a file already there, the same to the byte, is
    not kept twice; a different one with the same name gets " (2)"."""
    for e in os.listdir(src):
        a, b = os.path.join(src, e), os.path.join(dst, e)
        if os.path.isdir(a) and os.path.isdir(b):
            merge(a, b)
        elif os.path.isfile(a) and os.path.isfile(b) and same(a, b):
            os.remove(a)
        else:
            shutil.move(a, free(b))
    shutil.rmtree(src, ignore_errors=True)


def same(a, b):
    """Whether two files hold the same bytes (the size first, then the content, a megabyte at a time)."""
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    with open(a, "rb") as x, open(b, "rb") as y:
        while True:
            p, q = x.read(1 << 20), y.read(1 << 20)
            if p != q:
                return False
            if not p:
                return True
