"""files: a folder of the home → its items, each with its kind (ARCHITECTURE.md, "the table of kinds").

An item is a file, or a folder seen whole (Gab, 2026-11-01: "items are files"; "symbios is mostly a
file system"): an album is a folder of tracks with its cover, an artist a folder of albums, a memo a
folder in ~/Memos with its sound and its transcript, a show a folder in ~/Podcasts with its episodes,
each episode a sound with its card beside it (features/podcasts). The board does this work, not the
phone: one look inside each folder here costs nothing, from the phone it would be one request each.

    python3 files.py ~ Music      # the items of ~/Music, as /api/files answers them

Standard library only. Kinds: artist, album, show, folder, track, episode, memo, note, article,
picture, video, document, file.
"""
import datetime
import json
import os
import re
import sys

AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav", ".webm")
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".gif")
VIDEO = (".mp4", ".m4v", ".mkv", ".ogv")
COVERS = ("cover", "folder", "front", "albumart", "album")
FRONT = re.compile(r"^---\n(.*?)\n---\n?", re.S)
WHEN = re.compile(r"^(\d{4}-\d\d-\d\d)[ T](\d\d)[-:](\d\d)\s*")  # a memo's folder: "2026-10-31 16-34 Its title"


def card(path, limit=6000):
    """A markdown file's front matter (one key a line, JSON values kept) and its first lines of text."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read(limit)
    except OSError:
        return {}, ""
    head = FRONT.match(text)
    meta = {}
    for line in head.group(1).split("\n") if head else []:
        key, _, value = line.partition(": ")
        try:
            meta[key.strip()] = json.loads(value) if value[:1] in ('"', "[", "{") else value.strip()
        except ValueError:
            meta[key.strip()] = value.strip()
    body = text[head.end():] if head else text
    lines = [l.strip() for l in body.split("\n") if l.strip() and not l.lstrip().startswith("#")]
    return meta, " ".join(lines)[:160]


def seconds(raw):
    """"0:19", "43:11", "1:02:03" or 2591 → seconds, or None."""
    try:
        n = 0
        for part in str(raw).split(":"):
            n = n * 60 + float(part)
        return int(n) or None
    except (TypeError, ValueError):
        return None


def look(full):
    """What a folder holds, one level down: its sounds, pictures, folders, and the rest."""
    found = {"audio": [], "images": [], "dirs": [], "other": []}
    try:
        for e in os.scandir(full):
            if e.name.startswith("."):
                continue
            low = e.name.lower()
            found["dirs" if e.is_dir() else "audio" if low.endswith(AUDIO) else "images" if low.endswith(IMAGES) else "other"].append(e)
    except OSError:
        pass
    return found


def cover_of(rel, images):
    """The folder's picture: cover.jpg, folder.jpg… else the first one."""
    images = sorted(images, key=lambda e: e.name.lower())
    pick = next((e for e in images if os.path.splitext(e.name)[0].lower() in COVERS), images[0] if images else None)
    return rel + "/" + pick.name if pick else None


def inside_of(rel, sounds):
    """No picture in the folder: the cover inside its first sound that has one (tags.py), else None."""
    import tags
    for s in sorted(sounds, key=lambda e: e.name.lower()):
        got = tags.inside_cover(rel + "/" + s.name, s.path)
        if got:
            return got
    return None


def folder(home, rel, e):
    """A folder seen whole: a memo, a show, an album, an artist, or a plain folder."""
    path = (rel + "/" if rel else "") + e.name
    top = path.split("/")[0]
    inner = look(e.path)
    item = {"name": e.name, "path": path, "modified": int(e.stat().st_mtime * 1000)}
    if not rel or top == "Videos":  # next/: the home's own folders, and folders of films, are plain folders
        return {**item, "kind": "folder", "count": sum(len(v) for v in inner.values())}
    if top == "Memos" and rel == "Memos" and inner["audio"]:
        meta, text = card(os.path.join(e.path, "transcript.md"))
        when = WHEN.match(e.name)
        sound = inner["audio"][0]
        # its title, else the words after its time in the folder's name, else the board's own heading for it ("Memo, 23
        # November 2026, 17:48"): never an empty name (a memo too short to be titled showed blank in the Player, 23 Nov)
        stamp = when and datetime.datetime.strptime("%s %s:%s" % when.groups(), "%Y-%m-%d %H:%M")
        rest = (e.name[when.end():] if when else e.name).strip()
        return {**item, "kind": "memo", "name": meta.get("title") or rest or "Memo, %d %s" % (stamp.day, stamp.strftime("%B %Y, %H:%M")) if stamp else meta.get("title") or rest or e.name,
                "date": when and "%s %s:%s" % when.groups(), "duration": seconds(meta.get("duration")),
                "audio": path + "/" + sound.name, "size": sound.stat().st_size, "text": text}
    if inner["audio"]:
        kind = "show" if top == "Podcasts" else "album"
        out = {**item, "kind": kind, "count": len(inner["audio"]), "cover": cover_of(path, inner["images"]) or inside_of(path, inner["audio"])}
        if kind == "album" and "/" in rel:
            out["artist"] = rel.split("/")[-1]
        elif kind == "album" and rel and rel != top:
            out["artist"] = rel
        return out
    if top == "Music" and inner["dirs"]:  # an artist: a folder of albums. next/: no picture of its own (Gab, 23 Nov:
        return {**item, "kind": "artist", "count": len(inner["dirs"])}  # "The folder should not have an image because it's an artist")
    return {**item, "kind": "folder", "count": sum(len(v) for v in inner.values())}


def file(rel, e, cards):
    """A file: its kind from where it is and what it ends with."""
    path = (rel + "/" if rel else "") + e.name
    top = path.split("/")[0]
    stem, ext = os.path.splitext(e.name)
    ext = ext.lower()
    st = e.stat()
    item = {"name": stem, "path": path, "size": st.st_size, "modified": int(st.st_mtime * 1000)}
    if ext in AUDIO:
        if top == "Podcasts":
            meta = cards.get(stem, {})
            return {**item, "kind": "episode", "name": meta.get("title") or stem, "date": meta.get("published"),
                    "duration": seconds(meta.get("duration")), "position": seconds(meta.get("position"))}
        number = re.match(r"^(\d+)\s*[-.]?\s*", stem)
        return {**item, "kind": "track", "name": stem[number.end():] if number and number.end() < len(stem) else stem,
                "number": int(number.group(1)) if number else None}
    if ext == ".md":
        return {**item, "kind": "article" if top == "Articles" else "note"}
    if ext in IMAGES:
        return {**item, "kind": "picture"}
    if ext in VIDEO or (ext == ".webm" and top == "Videos"):
        return {**item, "kind": "video"}
    if ext == ".pdf":
        return {**item, "kind": "document"}
    return {**item, "kind": "file"}


def items(home, rel):
    """The items of a folder (rel to the home), folders seen whole first, then files, each with its kind."""
    rel = rel.strip("/")
    full = os.path.join(home, rel)
    entries = sorted((e for e in os.scandir(full) if not e.name.startswith(".")), key=lambda e: e.name.lower())
    stems = {os.path.splitext(e.name)[0] for e in entries if e.is_file() and e.name.lower().endswith(AUDIO)}
    cards = {}  # an episode's card beside it (features/podcasts), not an item of its own
    for e in entries:
        if e.is_file() and e.name.endswith(".md") and os.path.splitext(e.name)[0] in stems:
            cards[os.path.splitext(e.name)[0]] = card(e.path)[0]
    out = [folder(home, rel, e) for e in entries if e.is_dir()]
    out += [file(rel, e, cards) for e in entries if e.is_file() and not (e.name.endswith(".md") and os.path.splitext(e.name)[0] in cards)]
    # next/: the tracks of an album wear its cover (Gab, 23 Nov: "every track should inherit from the same image")
    if any(i["kind"] == "track" for i in out):
        cover = cover_of(rel, [e for e in entries if e.is_file() and e.name.lower().endswith(IMAGES)])
        import tags
        for i in out:
            if i["kind"] == "track":
                # no picture beside it: the cover inside the track itself, if it has one (Gab, 24 Nov)
                i["cover"] = cover or tags.inside_cover(i["path"], os.path.join(home, i["path"]))
    if rel == "Memos":
        out.sort(key=lambda i: i.get("date") or "", reverse=True)  # the newest memo first
    elif rel.split("/")[0] == "Podcasts":  # the shows, then the newest episode first
        out = [i for i in out if i["kind"] != "episode"] + sorted((i for i in out if i["kind"] == "episode"), key=lambda i: i.get("date") or "", reverse=True)
    elif any(i["kind"] == "track" for i in out):
        out.sort(key=lambda i: (i["kind"] != "track", i.get("number") or 0, i["name"].lower()))
    return {"path": rel, "items": out}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(items(os.path.expanduser(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else ""), indent=1, ensure_ascii=False))
