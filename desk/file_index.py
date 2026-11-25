"""file_index: the home's files, one row each, kept by the desk as things arrive and change.

Gab, 23 Nov, after dropping the same album twice: "we should make a dedupe, and I believe that if we do that
then we need an index of the files". Its first use is the dedupe; the same rows will give the launcher its file
search, Files the titles from the tags, and TermNL the files of the session.

Its own module, standard library only, nothing of the server in it: on the board it can sit under the desk's
server or under TermNL (ARCHITECTURE.md gives TermNL the files) as it is. (Gab: "as soon as we are not
overlapping with what we will do next on the board".)

    ix = Index(home)               # <home>/.desk/index.db, made on first use
    ix.add("Music/a.mp3", digest)  # a file the desk placed (its fingerprint when known: hashed while it arrived)
    ix.moved("Music/A", "Music/B") # a file or a folder renamed or moved
    ix.removed("Notes/old.md")     # a file or a folder gone (the trash)
    ix.has(digest)                 # where these bytes already are in the home, or None
    ix.check()                     # the gentle round: what changed on disk without the desk (a USB stick, scp)

Kept cheap for the board (an SD card, no fan): a row is written only when something changes; the round compares
size and date and fingerprints only what changed, one file at a time; a sound's tags are read once, from the file
(tags.py: ffprobe took a second a sound on the Lyra).
Hidden folders (the trash, the index itself) are not indexed.

A fingerprint is the SHA-256 of the bytes, as the desk's inbox already keeps them (desk/server.py, Inbox/.received).
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time

import tags

AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav", ".webm", ".wma")
SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  path TEXT PRIMARY KEY,   -- relative to the home, '/'-separated
  size INTEGER, mtime REAL,
  digest TEXT,             -- SHA-256 of the bytes
  artist TEXT, album TEXT, title TEXT, track INTEGER, duration REAL,  -- a sound's tags, read once
  added REAL
);
CREATE INDEX IF NOT EXISTS by_digest ON files (digest);
"""


def fingerprint(full):
    """The SHA-256 of a file, a megabyte at a time."""
    h = hashlib.sha256()
    with open(full, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sound_tags(full):
    """A sound's tags: read from the file (tags.py, MP3 M4A FLAC), else ffprobe for the rare others; {} without tags."""
    t = tags.read(full)
    if t is not None:
        return {"artist": t["album_artist"] or t["artist"], "album": t["album"], "title": t["title"],
                "track": t["track"], "duration": t["duration"]}
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                              "format=duration:format_tags=album_artist,artist,album,title,track",
                              "-of", "json", full], capture_output=True, text=True, timeout=20).stdout
        fmt = json.loads(out or "{}").get("format", {})
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    t = {k.lower(): v.strip() for k, v in fmt.get("tags", {}).items()}
    try:
        track = int(t.get("track", "").split("/")[0])
    except ValueError:
        track = None
    try:
        duration = round(float(fmt.get("duration")), 1)
    except (TypeError, ValueError):
        duration = None
    return {"artist": t.get("album_artist") or t.get("artist") or None, "album": t.get("album") or None,
            "title": t.get("title") or None, "track": track, "duration": duration}


class Index:
    def __init__(self, home):
        self.home = os.path.realpath(home)
        folder = os.path.join(self.home, ".desk")
        os.makedirs(folder, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(folder, "index.db"), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")  # whole after a power cut
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    def full(self, rel):
        return os.path.join(self.home, *rel.split("/"))

    def add(self, rel, digest=None):
        """A file the desk placed, or a folder's files: fingerprinted (unless known) and, for a sound, its tags."""
        full = self.full(rel)
        if os.path.isdir(full):
            for root, dirs, names in os.walk(full):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for n in names:
                    if not n.startswith("."):
                        self.add(os.path.relpath(os.path.join(root, n), self.home).replace(os.sep, "/"))
            return
        try:
            st = os.stat(full)
        except OSError:
            return
        tags = sound_tags(full) if full.lower().endswith(AUDIO) else {}
        digest = digest or fingerprint(full)
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (rel, st.st_size, st.st_mtime, digest, tags.get("artist"), tags.get("album"), tags.get("title"),
                             tags.get("track"), tags.get("duration"), time.time()))

    def moved(self, old, new):
        """A file or a folder renamed or moved: its rows follow."""
        with self.lock:
            self.db.execute("UPDATE files SET path = ? WHERE path = ?", (new, old))
            self.db.execute("UPDATE files SET path = ? || substr(path, ?) WHERE path LIKE ? ESCAPE '\\'",
                            (new, len(old) + 1, like(old) + "/%"))

    def removed(self, rel):
        with self.lock:
            self.db.execute("DELETE FROM files WHERE path = ? OR path LIKE ? ESCAPE '\\'", (rel, like(rel) + "/%"))

    def has(self, digest):
        """Where these bytes already are in the home (a path), or None."""
        with self.lock:
            row = self.db.execute("SELECT path FROM files WHERE digest = ? LIMIT 1", (digest,)).fetchone()
        return row[0] if row and os.path.exists(self.full(row[0])) else None

    def sounds(self, paths):
        """The tags kept for these files: {path: {"title", "track", "duration", "artist", "album"}}, the sounds only."""
        if not paths:
            return {}
        out = {}
        with self.lock:
            for i in range(0, len(paths), 500):
                part = paths[i:i + 500]
                for row in self.db.execute("SELECT path, title, track, duration, artist, album FROM files WHERE path IN (%s)"
                                           % ",".join("?" * len(part)), part):
                    if any(row[1:]):
                        out[row[0]] = dict(zip(("title", "track", "duration", "artist", "album"), row[1:]))
        return out

    def search(self, words, limit=40):
        """Files whose own name or title holds every word (in any order, any case): their paths, the best first
        (a name that starts with the words, then the shortest path). An album or an artist is found as its
        folder, by the server, not as each of its tracks."""
        words = [w for w in words.lower().split() if w][:6]
        if not words:
            return []
        with self.lock:  # the words narrow it in SQLite; the name is checked here
            rows = self.db.execute("SELECT path, title FROM files WHERE " + " AND ".join(
                ["lower(path || ' ' || coalesce(title,'')) LIKE ? ESCAPE '\\'"] * len(words)),
                ["%" + like(w) + "%" for w in words]).fetchall()
        hits = []
        for path, title in rows:
            own = (path.rsplit("/", 1)[-1] + " " + (title or "")).lower()
            if all(w in own for w in words):
                hits.append((not (title or path.rsplit("/", 1)[-1]).lower().lstrip("0123456789 -.").startswith(words[0]), len(path), path))
        return [h[2] for h in sorted(hits)[:limit]]

    def paths(self, word, limit=400):
        """Paths holding a word anywhere (their folders too), for the server to find folders by name."""
        with self.lock:
            return [r[0] for r in self.db.execute("SELECT path FROM files WHERE lower(path) LIKE ? ESCAPE '\\' LIMIT ?",
                                                  ("%" + like(word.lower()) + "%", limit))]

    def count(self):
        with self.lock:
            return self.db.execute("SELECT count(*) FROM files").fetchone()[0]

    def check(self, pause=0.0):
        """The gentle round: rows whose file is gone go; files new or changed on disk (size or date) are
        fingerprinted again, one at a time. Answers (added or changed, gone)."""
        with self.lock:
            known = {p: (s, m) for p, s, m in self.db.execute("SELECT path, size, mtime FROM files")}
        seen, changed = set(), 0
        for root, dirs, names in os.walk(self.home):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for n in sorted(names):
                if n.startswith("."):
                    continue
                full = os.path.join(root, n)
                rel = os.path.relpath(full, self.home).replace(os.sep, "/")
                seen.add(rel)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                if known.get(rel) != (st.st_size, st.st_mtime):
                    self.add(rel)
                    changed += 1
                    if pause:
                        time.sleep(pause)  # leave the board's CPU to what the person is doing
        gone = [p for p in known if p not in seen]
        with self.lock:
            self.db.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in gone])
        return changed, len(gone)


def like(text):
    """text, safe inside a LIKE pattern."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
