"""The home folder as the page and the phone see it: a folder's entries or items, a file's text or bytes, a text
saved from the Editor. Every path stays inside the home."""
import os
import re

import config
from tags import INSIDE, picture

TYPES = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json",
         ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".txt": "text/plain",
         ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
         ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".oga": "audio/ogg",
         ".opus": "audio/ogg", ".flac": "audio/flac", ".wav": "audio/wav",
         ".webm": "video/webm", ".mp4": "video/mp4", ".m4v": "video/mp4", ".ogv": "video/ogg", ".mkv": "video/x-matroska",
         ".mov": "video/quicktime"}


def inside(path):
    """A path asked by the page → the real path, only inside the home folder."""
    HOME = config.HOME
    full = os.path.realpath(os.path.join(HOME, path.lstrip("/")))
    if full != HOME and not full.startswith(HOME + os.sep):
        raise PermissionError("outside the home folder")
    return full


class FsRoutes:
    """The server's routes for the home's files (mixed into its handler). fs_get answers a route of its and says
    True, or leaves it to the server and says False; PermissionError and the like go up to the server's answer."""

    def fs_get(self, path, q):
        HOME = config.HOME
        if path == "/api/fs/list":
            full = inside(q.get("path", ""))
            entries = [{"name": e.name, "dir": e.is_dir(), "size": 0 if e.is_dir() else e.stat().st_size,
                        "modified": int(e.stat().st_mtime * 1000)}  # ms: the phone's Notes tell a note changed here
                       for e in os.scandir(full) if not e.name.startswith(".")]
            entries.sort(key=lambda e: (not e["dir"], e["name"].lower()))
            self.send({"path": "" if full == HOME else os.path.relpath(full, HOME), "entries": entries})
        elif path == "/api/files":  # a folder's items, each with its kind (files.py): what the phone's Player shows
            import files
            full = inside(q.get("path", ""))
            if not os.path.isdir(full):
                self.fail(404, "not found")
            else:
                self.send(files.items(HOME, "" if full == HOME else os.path.relpath(full, HOME)))
        elif path == "/api/fs/raw" and q.get("path", "").endswith(INSIDE):  # the cover inside a sound (tags.py)
            full = inside(q["path"][:-len(INSIDE)])
            got = picture(full) if os.path.isfile(full) else None
            if not got:
                self.fail(404, "no cover inside this sound")
            else:
                self.send(got[0], got[1])
        elif path == "/api/fs/raw":
            full = inside(q.get("path", ""))
            if not os.path.isfile(full):
                self.fail(404, "not found")
            else:
                self.raw(full)
        elif path == "/api/fs/read":
            full = inside(q.get("path", ""))
            if os.path.getsize(full) > 200_000:
                self.fail(413, "too large to show")
            else:
                self.send({"text": open(full, encoding="utf-8", errors="replace").read()})
        else:
            return False
        return True

    def raw(self, full):
        """A file as it is, for <audio> and <img>. Answers Range requests so a track can be
        sought, and sends in pieces so a long one never sits whole in memory. Asked sealed, it is
        sealed whole, no Range (SECURE-LINK.md, known limits)."""
        if self.sid:
            if os.path.getsize(full) > config.SEALED_MOST:
                return self.fail(413, "too large to send sealed")
            with open(full, "rb") as f:
                return self.send(f.read())
        size = os.path.getsize(full)
        start, end = 0, size - 1
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start, end = int(m.group(1)), min(int(m.group(2) or end), end)
            else:
                start = max(0, size - int(m.group(2)))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", "bytes */%d" % size)
                self.end_headers()
                return
        self.send_response(206 if m else 200)
        kind = TYPES.get(os.path.splitext(full)[1].lower(), "application/octet-stream")
        self.send_header("Content-Type", kind)
        self.send_header("Accept-Ranges", "bytes")
        # never run as the desk: a page or a drawing of the home opened from here is sandboxed, its type not guessed
        # (symbios SECURITY.md, review of 24 Nov, C2: an .svg or .html linked from a note ran with the desk's pass)
        self.send_header("X-Content-Type-Options", "nosniff")
        if not kind.startswith("application/pdf"):
            self.send_header("Content-Security-Policy", "sandbox")
        if self.headers.get("Origin") in config.COMPANION:  # the phone keeps a deck's previews (see send)
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Vary", "Origin")
        self.send_header("Content-Length", str(end - start + 1))
        if m:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        with open(full, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                piece = f.read(min(65536, left))
                if not piece:
                    break
                try:
                    self.wfile.write(piece)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the player moved on
                left -= len(piece)

    def write(self, body):
        """Save a text file from the editor: inside the home folder, text only, 1 MB at most."""
        try:
            full, text = inside(body["path"]), body["text"]
            if not isinstance(text, str) or len(text) > 1_000_000 or full == config.HOME or os.path.isdir(full):
                return self.fail(400, "not a text file that can be saved here")
            tmp = full + ".saving"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, full)  # the old file stays whole if the write is cut short
            self.send({"saved": True, "size": os.path.getsize(full), "modified": int(os.path.getmtime(full) * 1000)})
        except (KeyError, TypeError):
            self.fail(400, "expected {\"path\": \"…\", \"text\": \"…\"}")
        except PermissionError as e:
            self.fail(403, str(e))
        except FileNotFoundError:
            self.fail(404, "that folder doesn't exist")
