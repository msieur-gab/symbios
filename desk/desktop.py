"""The desktop on the file system (from symbios/next/, the fold, step 2): a folder's items as Files shows them, the
launcher's search, a file as it is, a drop placed by the rulebook (place.py) and kept once (file_index.py), the
home's folders changed by hand (a new folder, a move, a rename, the trash), and the quick panel's WiFi, sound,
Bluetooth and mesh node. Gab, 23 Nov: "it looks to be sturdy enough to become the new desk for our boards."

GET  /api/items?path=           a folder's items, each with its kind (files.py, the table of kinds), sounds titled from their tags
GET  /api/search?q=             files and folders of the home whose names (or a sound's tags) hold the words (file_index.py)
GET  /api/raw?path=             a file as it is, ranges answered (sound and film can be sought), never run as the desk
GET  /api/wifi, /api/wifi/scan  where the device is and what it knows; what is in range (wifi.py)
POST /api/wifi/add {"ssid", "password"}, /api/wifi/forget {"ssid"}   near only (the board's screen, its cable)
GET  /api/volume, POST /api/volume {"level", "muted"}   the sound's level (devices.py)
GET  /api/bluetooth, /api/mesh  what is connected: the Bluetooth devices, a Meshtastic node on USB (devices.py)
POST /api/drop?batch=&path=     one dropped file, streamed into the drop's own folder (path as dropped: "Album/01.mp3")
POST /api/drop/done?batch=&into=  the drop is complete: into a folder when given, else each thing where the rulebook says
POST /api/drop/cancel?batch=    stopped: what had arrived of it goes
POST /api/folder {"path"}, /api/move {"paths", "into"}, /api/rename {"path", "name"}, /api/trash {"paths"}
GET  /api/prefs, POST /api/prefs {key: value}   the person's preferences, the same on every screen (prefs.py)
"""
import hashlib
import mimetypes
import os
import re
import shutil
import sys
import threading
import time

import config
import devices
import file_index
import files
import prefs
import place
import wifi
from shell import near

FOLDERS = ("Documents", "Music", "Pictures", "Videos", "Notes", "Memos", "Downloads", "Inbox")
KEPT = FOLDERS + ("Articles", "Slides", "Podcasts", "Mesh")  # the home's own folders, the desk's too: never to the trash
DROPS = ".drops"
TRASH = ".Trash"
KEEP_FREE = 200 * 1024 * 1024  # a drop that would leave less than this on the disk is refused
mimetypes.add_type("text/markdown", ".md")
mimetypes.add_type("audio/mp4", ".m4a")
mimetypes.add_type("audio/flac", ".flac")
mimetypes.add_type("audio/ogg", ".opus")

IX = None  # the index of the home's files (file_index.py), opened by start()
STAGED = {}  # a file of a drop in its staging folder → its fingerprint, worked out while it arrived


class Refused(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def start(home):
    """The home's own folders, the rulebook, the index and its rounds; drops cut short last time go."""
    global IX
    for name in FOLDERS:
        os.makedirs(os.path.join(home, name), exist_ok=True)
    place.rules(os.path.join(home, "Inbox"))  # the rulebook, written once
    shutil.rmtree(os.path.join(home, DROPS), ignore_errors=True)
    IX = file_index.Index(home)
    threading.Thread(target=rounds, args=(IX,), daemon=True).start()


def rounds(ix):
    """The index's gentle round: at start, then every ten minutes, what changed without the desk."""
    while True:
        t = time.time()
        try:
            changed, gone = ix.check(pause=0.02)
            sys.stderr.write("index: %d files, %d new or changed, %d gone (%.1f s)\n" % (ix.count(), changed, gone, time.time() - t))
        except Exception as e:  # the round never takes the desk down
            sys.stderr.write("index: round failed: %r\n" % e)
        time.sleep(600)


def name_ok(name):
    name = (name or "").strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith(".") or len(name) > 200:
        raise Refused(400, "not a name: " + repr(name))
    return name


class DesktopRoutes:
    """The server's routes for the desktop (mixed into its handler). desktop_get, desktop_drop and desktop_post
    answer a route of theirs and say True, or leave it to the server and say False."""

    # ---- the home's paths: always inside it, never hidden ones ----
    def home_path(self, rel, hidden=False, must_exist=True):
        home = config.HOME
        rel = (rel or "").strip("/")
        parts = [p for p in rel.split("/") if p]
        if any(p in (".", "..") for p in parts) or (not hidden and any(p.startswith(".") for p in parts)):
            raise Refused(400, "not a path of the home: " + rel)
        full = os.path.realpath(os.path.join(home, *parts))
        if full != home and not full.startswith(home + os.sep):
            raise Refused(400, "not a path of the home: " + rel)
        if must_exist and not os.path.exists(full):
            raise Refused(404, "nothing at " + rel)
        return full

    def rel(self, full):
        return os.path.relpath(full, config.HOME).replace(os.sep, "/")

    def answered(self, fn, *args):
        """fn's answer sent, or its refusal: True either way."""
        try:
            got = fn(*args)
            if got is not None:
                self.send(got)
        except Refused as e:
            self.fail(e.status, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # said, and the page gets an answer
            sys.stderr.write("desk: %s %s: %r\n" % (self.command, self.path, e))
            self.fail(500, str(e))
        return True

    # ---- reading ----
    def desktop_get(self, path, q):
        if path == "/api/items":
            return self.answered(self.items, q.get("path"))
        if path == "/api/search":
            return self.answered(self.search, q.get("q", ""))
        if path == "/api/raw":
            import tags
            if (q.get("path") or "").endswith(tags.INSIDE):  # the cover inside a sound (tags.py)
                return self.answered(lambda: self.inside_picture(self.home_path(q["path"][:-len(tags.INSIDE)])))
            return self.answered(lambda: self.home_raw(self.home_path(q.get("path"))))
        if path == "/api/wifi":
            return self.answered(wifi.status)
        if path == "/api/wifi/scan":
            return self.answered(wifi.scan)
        if path == "/api/bluetooth":
            return self.answered(devices.bluetooth)
        if path == "/api/mesh":  # the radios on USB (a bootloader too), and the one Mesh is talking to (mesh/)
            return self.answered(lambda: {**devices.mesh(), "radio": self.mesh_radio()})
        if path == "/api/volume":
            return self.answered(devices.volume)
        if path == "/api/prefs":
            return self.answered(prefs.read)
        return False

    def items(self, rel):
        full = self.home_path(rel)
        if not os.path.isdir(full):
            raise Refused(400, "not a folder")
        return self.titled(files.items(config.HOME, self.rel(full) if full != config.HOME else ""))

    def titled(self, listing):
        """A folder's items with what the index keeps of its sounds: a track's title, number and length from its tags
        (Gab, 23 Nov: "it seems like we are not reading the ID3 tags"), where the file's name said less."""
        tags = IX.sounds([i["path"] for i in listing["items"] if i["kind"] in ("track", "episode")])
        for i in listing["items"]:
            t = tags.get(i["path"])
            if not t:
                continue
            if t["title"] and i["kind"] == "track":
                i["name"] = t["title"]
            if t["track"] and not i.get("number"):
                i["number"] = t["track"]
            if t["duration"] and not i.get("duration"):
                i["duration"] = t["duration"]
        if any(i["kind"] == "track" for i in listing["items"]):
            listing["items"].sort(key=lambda i: (i["kind"] != "track", i.get("number") or 0, i["name"].lower()))
        return listing

    def search(self, words):
        """The launcher's search: the folders whose name holds the words, then the files (file_index.py), each as
        Files would show it (its kind, its cover), with where it is."""
        words = words.strip()
        if len(words) < 2:
            return {"items": []}
        paths = IX.search(words)
        low = words.lower().split()
        folders, seen = [], set()
        for p in IX.paths(low[0]):  # a folder matches by its own name
            parts = p.split("/")[:-1]
            for n in range(1, len(parts) + 1):
                f = "/".join(parts[:n])
                if f not in seen and all(w in parts[n - 1].lower() for w in low):
                    seen.add(f)
                    folders.append(f)
        out, listed = [], {}
        def entry(path):  # the item as Files shows it, from its folder's listing (one listing per folder)
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent not in listed:
                try:
                    listed[parent] = {i["path"]: i for i in self.titled(files.items(config.HOME, parent))["items"]}
                except OSError:
                    listed[parent] = {}
            return listed[parent].get(path)
        for p in folders[:8] + paths[:20]:
            i = entry(p)
            if i:
                out.append({**i, "where": p.rsplit("/", 1)[0] if "/" in p else "Home"})
        return {"items": out}

    def inside_picture(self, full):
        """The cover inside a sound (MP3, M4A, FLAC), as a picture of a type the browser shows; 404 when there is none."""
        import tags
        got = tags.picture(full) if os.path.isfile(full) else None
        if not got:
            raise Refused(404, "no cover inside this sound")
        self.send(got[0], got[1])

    def home_raw(self, full):
        """A file as it is, ranges answered, in pieces. Never run as the desk: a page or a drawing of the home is
        sandboxed (the shell is one tab away), the type is not guessed by the browser."""
        if not os.path.isfile(full):
            raise Refused(400, "not a file")
        size = os.path.getsize(full)
        kind = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if kind.startswith("text/"):
            kind += "; charset=utf-8"
        start, end, status = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if m and size:
            if m.group(1):
                start = int(m.group(1))
                end = min(int(m.group(2)), size - 1) if m.group(2) else size - 1
            else:  # the last N bytes
                start = max(0, size - int(m.group(2) or 0))
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(end - start + 1 if size else 0))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        if not kind.startswith("application/pdf"):  # the browser's PDF reader needs it off
            self.send_header("Content-Security-Policy", "sandbox")
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        if not size:
            return
        with open(full, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1024 * 256, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the player moved on
                left -= len(chunk)

    # ---- a drop: its files stream in one by one (no JSON body) ----
    def desktop_drop(self, path, q):
        if path == "/api/drop":
            return self.answered(self.drop, q)
        if path == "/api/drop/done":
            return self.answered(self.done, q)
        if path == "/api/drop/cancel":  # stopped from the page: what had arrived goes
            return self.answered(lambda: shutil.rmtree(self.staging(q.get("batch")), ignore_errors=True) or {"ok": True})
        return False

    def staging(self, batch):
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", batch or ""):
            raise Refused(400, "no drop")
        return os.path.join(config.HOME, DROPS, batch)

    def drop(self, q):
        """One file of a drop, streamed to <home>/.drops/<batch>/<its path as dropped>."""
        stage = self.staging(q.get("batch"))
        parts = [p for p in (q.get("path") or "").replace("\\", "/").split("/") if p]
        if not parts or any(p in (".", "..") for p in parts):
            raise Refused(400, "no file name")
        n = int(self.headers.get("Content-Length") or -1)
        if n < 0:
            raise Refused(411, "the size first")
        if shutil.disk_usage(config.HOME).free - n < KEEP_FREE:
            raise Refused(507, "not enough room on the disk")
        target = os.path.join(stage, *parts)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        part = target + ".part"
        left, digest = n, hashlib.sha256()
        with open(part, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(1024 * 1024, left))
                if not chunk:
                    break
                f.write(chunk)
                digest.update(chunk)  # its fingerprint as it arrives: no second reading
                left -= len(chunk)
        if left:
            os.remove(part)
            raise Refused(400, "the file stopped arriving")
        os.replace(part, target)
        STAGED[target] = digest.hexdigest()
        if q.get("modified", "").isdigit():
            t = int(q["modified"]) / 1000
            os.utime(target, (t, t))
        return {"ok": True}

    def done(self, q):
        """The drop is all here: each thing at its top goes into `into`, or where the rulebook says. A thing whose
        every file is already on the desk (the same bytes, anywhere in the home) is not stored again: the answer
        says where it is (Gab, 23 Nov: "we should make a dedupe")."""
        home = config.HOME
        stage = self.staging(q.get("batch"))
        if not os.path.isdir(stage):
            raise Refused(404, "nothing dropped")
        into = self.home_path(q["into"]) if q.get("into") else None
        out = []
        try:
            for name in sorted(os.listdir(stage)):
                if name.endswith(".part"):
                    continue
                path = os.path.join(stage, name)
                prints = self.prints(path)  # inner path ("" for a file) → fingerprint
                there = [IX.has(d) for d in prints.values()]
                if prints and all(there):
                    shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
                    first = there[0]
                    out.append({"name": name, "already": first, "went": first.rsplit("/", 1)[0] if "/" in first else "", "path": first, "left": []})
                    continue
                if into:
                    folder = into
                    if os.path.dirname(into) == home and os.path.basename(into).lower() == "music":  # dropped on Music itself: by artist too
                        folder = place.by_artist(into, path, place.majority(path) if os.path.isdir(path) else path) or into
                        os.makedirs(folder, exist_ok=True)
                    target = place.free(os.path.join(folder, name))
                    shutil.move(path, target)
                    got = {"name": name, "went": self.rel(folder), "path": self.rel(target), "left": []}
                else:
                    got = place.settle(home, path, "desk")
                self.index(got["path"], prints)
                out.append(got)
        finally:
            for k in [k for k in STAGED if k.startswith(stage + os.sep)]:
                STAGED.pop(k, None)
            shutil.rmtree(stage, ignore_errors=True)
        return {"placed": out}

    def prints(self, path):
        """The fingerprints of what a drop holds: {inner path: fingerprint}, "" for a lone file."""
        if os.path.isfile(path):
            return {"": STAGED.get(path) or file_index.fingerprint(path)}
        out = {}
        for root, dirs, names in os.walk(path):
            for n in names:
                full = os.path.join(root, n)
                out[os.path.relpath(full, path).replace(os.sep, "/")] = STAGED.get(full) or file_index.fingerprint(full)
        return out

    def index(self, rel, prints):
        """What was just placed, into the index, with the fingerprints worked out as it arrived. A zip's files, or
        a file renamed on the way, are fingerprinted again."""
        full = self.home_path(rel)
        if os.path.isfile(full):
            return IX.add(rel, prints.get(""))
        for root, dirs, names in os.walk(full):
            for n in names:
                inner = os.path.relpath(os.path.join(root, n), full).replace(os.sep, "/")
                IX.add(rel + "/" + inner, prints.get(inner))

    # ---- changing (a JSON body) ----
    def desktop_post(self, path, b):
        if path not in ("/api/prefs", "/api/volume", "/api/wifi/add", "/api/wifi/forget", "/api/folder", "/api/move", "/api/rename", "/api/trash"):
            return False
        if not isinstance(b, dict):
            return self.fail(400, "expected {…}") or True
        return self.answered(self.change, path, b)

    def change(self, path, b):
        home = config.HOME
        if path == "/api/prefs":
            try:
                return prefs.change(b)
            except ValueError as e:
                raise Refused(400, str(e))
        if path == "/api/volume":
            try:
                return devices.set_volume(b.get("level"), b.get("muted") if isinstance(b.get("muted"), bool) else None)
            except (TypeError, ValueError):
                raise Refused(400, "a level from 0 to 100")
        if path in ("/api/wifi/add", "/api/wifi/forget"):
            if not near(self):  # anyone let in may see where the board is; only near may change it
                raise Refused(403, "WiFi is set on the device itself or over its USB cable")
            ssid, password = str(b.get("ssid") or "").strip(), str(b.get("password") or "")
            if not ssid:
                raise Refused(400, "which network?")
            return wifi.change(path.rsplit("/", 1)[1], ssid, password)
        if path == "/api/folder":
            parent, _, name = (b.get("path") or "").strip("/").rpartition("/")
            target = os.path.join(self.home_path(parent), name_ok(name))
            if os.path.exists(target):
                raise Refused(409, "there is already something called " + name)
            os.makedirs(target)
            return {"path": self.rel(target)}
        if path == "/api/move":
            into = self.home_path(b.get("into"))
            if not os.path.isdir(into):
                raise Refused(400, "not a folder: " + str(b.get("into")))
            moved = []
            for rel in b.get("paths") or []:
                src = self.home_path(rel)
                if src == home or into == src or into.startswith(src + os.sep):
                    raise Refused(400, "a folder can't go inside itself: " + rel)
                if os.path.dirname(src) == into:
                    continue
                target = place.free(os.path.join(into, os.path.basename(src)))
                shutil.move(src, target)
                IX.moved(self.rel(src), self.rel(target))
                moved.append(self.rel(target))
            return {"moved": moved}
        if path == "/api/rename":
            src = self.home_path(b.get("path"))
            if src == home:
                raise Refused(400, "the home keeps its name")
            target = os.path.join(os.path.dirname(src), name_ok(b.get("name")))
            if os.path.exists(target) and os.path.realpath(target) != src:
                raise Refused(409, "there is already something called " + b.get("name"))
            os.rename(src, target)
            IX.moved(self.rel(src), self.rel(target))
            return {"path": self.rel(target)}
        if path == "/api/trash":
            trash = os.path.join(home, TRASH)
            os.makedirs(trash, exist_ok=True)
            gone = []
            for rel in b.get("paths") or []:
                src = self.home_path(rel)
                if src == home or os.path.dirname(src) == home and os.path.basename(src) in KEPT:
                    raise Refused(400, "the home's own folders stay: " + rel)
                shutil.move(src, place.free(os.path.join(trash, os.path.basename(src))))
                IX.removed(self.rel(src))
                gone.append(rel)
            return {"trashed": gone}
