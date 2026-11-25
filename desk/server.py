"""desk: the device side of a small desktop in the browser. Serves the page, answers what is said to TermNL
(on this device: it understands, asks, and runs its skills' commands), lists the home folder, and runs the
commands the page's skills hand over. Standard library only.

    python3 server.py                      # files and status run for real, the rest is simulated
    python3 server.py --allow all          # on a board of its own: power too
    python3 server.py --home ~ --termnl ~/TermNL --port 80

What protects the device: the lock in front of every route (lock.py, trust.py; SECURE-LINK.md), and what a
command may be (commands.py, FORMS): only the commands the skills declare, values in single quotes, no shell
tricks. The Terminal's real shell (shell.py) opens only for the networks --shell names: this device by default,
and on a board the USB cable too. Never the WiFi.

This file is the lock in front (gate), the routing, and the start. What each route does is in its module, mixed
into the handler: lock.py (screens, the claim), desktop.py (Files, drops, the quick panel), fs.py (the home's files
as the phone and the old page read them), receive.py (a file arriving in the
Inbox), shell.py, talk.py (TermNL and Ask), commands.py (/api/exec), status.py (the board's numbers), show.py (the slide on
show), music.py. What they share (the home, the options) is in config.py.
"""
import argparse
import io
import ipaddress
import json
import os
import secrets
import stat
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import config
import trust
import desktop
from commands import FORMS, CommandRoutes
from desktop import DesktopRoutes
from fs import TYPES, FsRoutes
from lock import LockRoutes, screen_pass, watch_screens
from music import music
from receive import InboxRoutes
from shell import ShellRoutes, near
from show import follow_slides, steer_slides
from status import status
from talk import Below, TalkRoutes, talk

# Every route is locked behind the secure link (SECURE-LINK.md, step 3) but these, and the page itself (a GET outside
# /api/: its code, not the person's content). Over the WiFi only the owner's phone, its request sealed, gets in; the
# board's own screen and the USB cable (--near) still pass as they are, until a screen is unlocked by the phone (step 5).
# A route added later is locked from the start. /api/hello gives the list, so the companion learns it from here.
OPEN = {"GET /api/hello", "POST /api/trust/claim", "POST /api/trust/session",
        "GET /api/screen", "POST /api/screen/ask", "GET /api/screen/wait"}  # the lock screen's own (step 5)


MESH = None  # Mesh, the desk's own part for a Meshtastic radio (mesh/), started with the server


class Handler(LockRoutes, DesktopRoutes, FsRoutes, InboxRoutes, ShellRoutes, TalkRoutes, CommandRoutes, BaseHTTPRequestHandler):
    def mesh_radio(self):
        """The radio Mesh is talking to, for the quick panel (desktop.py, GET /api/mesh), or None."""
        return MESH.summary() if MESH else None

    def send(self, body, kind="application/json", code=200, n=None, cookie=None):
        data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body)).encode()
        if getattr(self, "sid", None) and code < 400:  # an answer to a sealed request is sealed too; a refusal isn't
            try:
                n, data = trust.seal(self.sid, self.route, data)
            except trust.Refused:  # the session ended while the request waited (the desk released, taken over, reset)
                self.sid = None
                return self.send({"error": "session unknown"}, code=401)
            kind = "application/octet-stream"
        self.send_response(code)
        self.send_header("Content-Type", kind + ("" if kind.startswith(("image/", "font/", "application/octet")) else "; charset=utf-8"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if n is not None:  # a sealed answer: its number, which the phone needs to open it
            self.send_header("X-N", str(n))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        if self.headers.get("Origin") in config.COMPANION:  # the phone's companion page may read the answer
            self.send_header("Access-Control-Allow-Origin", self.headers["Origin"])
            self.send_header("Access-Control-Expose-Headers", "X-N")
            self.send_header("Vary", "Origin")
        try:
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page went away while it waited (closed, reloaded): nothing to answer, nothing to log

    def do_OPTIONS(self):
        """What a browser asks first, before it lets the companion page (https, elsewhere) call
        the desk (plain http, on the local network): is this page expected here?"""
        origin = self.headers.get("Origin")
        if origin not in config.COMPANION:
            return self.fail(403, "not a page the desk expects")
        self.send_response(204)
        for name, value in (("Access-Control-Allow-Origin", origin), ("Access-Control-Allow-Methods", "GET, POST"),
                            ("Access-Control-Allow-Headers", "Content-Type, X-Session, X-N, X-Seal"), ("Access-Control-Allow-Private-Network", "true"),
                            ("Access-Control-Max-Age", "600"), ("Vary", "Origin"), ("Content-Length", "0")):
            self.send_header(name, value)
        self.end_headers()

    def fail(self, code, why):
        self.send({"error": why}, code=code)

    def gate(self, method):
        """In front of every request. A sealed one (X-Session, X-N; a GET's seal in X-Seal) is opened here, bound to its method and full path,
        ?name= and all, and goes on as if it had come plain; its answer is sealed in send(). A plain one to a locked
        route goes on only from nearby. False when refused (the answer already sent)."""
        self.sid, self.route = None, method + " " + self.path
        sid = self.headers.get("X-Session")
        if sid:
            try:
                size, n = int(self.headers.get("Content-Length", 0)), int(self.headers.get("X-N", ""))
                if size > config.SEALED_MOST:
                    self.fail(413, "too large")
                    return False
                # a GET can't carry a body from a browser: its seal (a request with no text: the proof alone) comes as X-Seal
                sealed = trust.unb64(self.headers.get("X-Seal", "")) if method == "GET" else self.rfile.read(size)
                text = trust.unseal(sid, n, self.route, sealed)
            except ValueError:
                self.fail(400, "expected a sealed message")
                return False
            except trust.Refused as e:
                sys.stderr.write("trust: %s refused: %s\n" % (self.route.split("?")[0], e))
                # an unknown session (the desk restarted, or it was forgotten): the phone opens a new one
                self.fail(401 if str(e) == "no such session" else 403, "session unknown" if str(e) == "no such session" else "refused")
                return False
            self.sid, self.rfile = sid, io.BytesIO(text)
            del self.headers["Content-Length"]
            self.headers["Content-Length"] = str(len(text))
            return True
        path = urlparse(self.path).path
        if method + " " + path in OPEN or (method == "GET" and not path.startswith("/api/")):
            return True  # the page itself, finding the desk, the claim, the lock screen
        if config.LOCAL and secrets.compare_digest(self.headers.get("X-Desk-Local", ""), config.LOCAL):
            return True  # the board's own programs
        # before the claim, the board's own screen and the cable get in as they are; after it, a screen the owner allowed
        if (self.nearby() if not trust.claimed() else screen_pass(self)):
            return True
        self.fail(403, "locked: only the desk's owner gets in here, through the companion")
        return False

    def do_GET(self):
        if not self.gate("GET"):
            return
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        HOME = config.HOME
        try:
            if url.path == "/api/hello":  # the companion knocks on every address of a network; the desk says it is here
                return self.send({"desk": True, "host": os.uname().nodename, "companion": sorted(config.COMPANION),
                                  "claimed": trust.claimed(), "word": trust.has_word(), "board": trust.key_id(trust.unb64(trust.board_key())),
                                  "open": sorted(OPEN)})
            if self.lock_get(url.path, q):  # the lock screen, the claim code, the phone's list of screens (lock.py)
                return
            if url.path == "/api/status":
                return self.send(status())
            if url.path == "/api/info":
                return self.send({"home": HOME, "allowed": sorted(config.ALLOWED), "groups": sorted(FORMS), "shell": near(self)})
            if url.path == "/api/shell":
                return self.shell()
            if self.fs_get(url.path, q):  # a folder's entries or items, a file's text or bytes (fs.py)
                return
            if self.desktop_get(url.path, q):  # Files, the launcher's search, the quick panel (desktop.py)
                return
            if url.path == "/api/ask":
                return self.ask(q.get("q", ""))
            if url.path == "/api/articles":
                import article
                return self.send({"articles": article.shelf(os.path.join(HOME, "Articles"))})
            if url.path == "/api/slides":  # the decks, and those still being made ("preparing": not to open yet)
                import inbox as router
                import slides
                names = slides.shelf(os.path.join(HOME, "Slides"))
                preparing = [n for n in names if not router.deck_ready(os.path.join(HOME, "Slides", n))]
                return self.send({"decks": names, "preparing": preparing, "now": follow_slides(-1, 0)})
            if url.path == "/api/slides/deck":  # a deck whose slides are made; one being made answers 409, preparing
                import inbox as router
                import slides
                name = q.get("name", "")
                if name not in slides.shelf(os.path.join(HOME, "Slides")):
                    return self.fail(404, "no such deck")
                if not router.deck_ready(os.path.join(HOME, "Slides", name)):
                    return self.send({"error": "“%s” is being prepared" % name, "preparing": True}, code=409)
                return self.send({**slides.prepare(os.path.join(HOME, "Slides", name)), "path": "Slides/%s/.deck/" % name})
            if url.path == "/api/changes":  # what happened after N: files placed, memos and decks made, the tasks (signals.py)
                import signals
                try:
                    after, boot = int(q.get("after", -1)), int(q.get("boot", 0))
                except ValueError:
                    return self.fail(400, "expected ?after=<number>&boot=<number>")
                return self.send(signals.since(after, boot))
            if url.path == "/api/slides/now":  # waits until the slide changes (or 25 s): the screens and the phone follow it
                return self.send(follow_slides(int(q.get("after", -1))))
            if url.path == "/api/music":
                return self.send({"tracks": music(q.get("q", ""))})
            if url.path == "/api/addons":  # the windows the add-ons bring (addons.py, desk.conf)
                return self.send(addons.apps())
            hit = (MESH and MESH.handle("GET", url.path, q, None)) or addons.route("GET", url.path, q, None)  # Mesh's, then an add-on's
            if hit:
                return self.send(hit[1], code=hit[0])
            if url.path.startswith("/addons/"):  # an add-on's own window files
                full = addons.file(url.path)
                if not full:
                    return self.fail(404, "not found")
                return self.send(open(full, "rb").read(), TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
            # the page itself: the desk (web/), and the old one at /old/ for the apps it still has alone (app/)
            root, rel = (config.OLD, url.path[len("/old/"):]) if url.path.startswith("/old/") else (config.APP, url.path.lstrip("/"))
            rel = rel or "index.html"
            full = os.path.realpath(os.path.join(root, rel))
            if not full.startswith(root + os.sep) or not os.path.isfile(full):
                return self.fail(404, "not found")
            return self.send(open(full, "rb").read(), TYPES.get(os.path.splitext(full)[1], "application/octet-stream"))
        except PermissionError as e:
            self.fail(403, str(e))
        except (FileNotFoundError, NotADirectoryError):
            self.fail(404, "not found")
        except IsADirectoryError:
            self.fail(400, "that is a folder")

    def do_POST(self):
        if not self.gate("POST"):
            return
        route = urlparse(self.path).path
        if route == "/api/inbox":
            return self.inbox()
        if self.desktop_drop(route, {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}):  # a drop (desktop.py)
            return
        if self.lock_post_plain(route):  # the phone's sealed hello, a lock screen's code, the Lock button (lock.py)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self.fail(400, "expected JSON")
        if route == "/api/fs/write":
            return self.write(body)
        if route == "/api/articles":
            return self.article(body)
        if route == "/api/slides":
            try:
                return self.send(steer_slides(str(body["do"])))
            except (KeyError, TypeError, AttributeError):
                return self.fail(400, "expected {\"do\": \"next\"}")
            except ValueError as e:
                return self.fail(422, str(e))
            except (OSError, subprocess.SubprocessError):
                return self.fail(500, "the deck couldn't be prepared (is pdftoppm installed?)")
        if self.desktop_post(route, body):  # a folder made, moved, renamed or trashed; the WiFi, the sound (desktop.py)
            return
        if self.lock_post(route, body):  # the phone: screens, the claim, the secret word, its session (lock.py)
            return
        if route in ("/api/say", "/api/reset"):  # TermNL's own API, answered here
            return self.say(body, reset=route == "/api/reset")
        hit = (MESH and MESH.handle("POST", route, {}, body)) or addons.route("POST", route, {}, body)  # Mesh's, then an add-on's (addons.py)
        if hit:
            return self.send(hit[1], code=hit[0])
        if route != "/api/exec":
            return self.fail(404, "not found")
        return self.exec(body)

    def article(self, body):
        """A web address → its article as markdown in ~/Articles, made here on the board
        (article.py: fetch, keep the article, write brainboard's front matter above it)."""
        import article
        HOME = config.HOME
        try:
            a = article.read(body["url"].strip())
        except (KeyError, AttributeError, TypeError):
            return self.fail(400, "expected {\"url\": \"…\"}")
        except ImportError:
            return self.fail(501, "this device lacks python3-readability and python3-html2text")
        except ValueError as e:
            return self.fail(422, str(e))
        except Exception:
            return self.fail(502, "that page couldn't be read")
        os.makedirs(os.path.join(HOME, "Articles"), exist_ok=True)
        path = os.path.join("Articles", article.name(a))
        with open(os.path.join(HOME, path), "w", encoding="utf-8") as f:
            f.write(article.text(a))
        import signals
        signals.publish("Articles", os.path.basename(path))  # the Reader and the phone hear of it
        import voice
        voice.announce(os.path.join(HOME, path), HOME)  # in Activity now, its embedding at the worker's next turn
        self.send({"saved": True, "path": path, "title": a["title"], "words": len(a["markdown"].split())})

    def log_message(self, fmt, *args):
        if "/api/status" not in (args[0] if args else ""):
            sys.stderr.write("%s  %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    conf = config.conf
    HERE = config.HERE
    ap = argparse.ArgumentParser(description="desk: page, files and commands for one device")
    ap.add_argument("--home", default=os.path.join(HERE, "home"), help="the folder the skills work in (default: home/ here, a sandbox)")
    ap.add_argument("--termnl", default=os.path.join(os.path.dirname(HERE), "TermNL"), help="what is said to the desk: TermNL's folder, "
                    "loaded inside this server (default: TermNL next to this one), or the socket TermNL's own service answers on "
                    "(SymbiOS: /run/symbios/termnl.sock)"),
    ap.add_argument("--allow", default="files,status", help="groups that really run: %s, or all" % ", ".join(FORMS))
    ap.add_argument("--shell", default="127.0.0.0/8", help="networks the Terminal's real shell opens for, or off "
                    "(default: this device only; a board adds its USB cable, 10.55.0.0/24)")
    ap.add_argument("--companion", default=conf().get("companion", "none"), help="where the phone's companion page lives: "
                    "the only sites allowed to call the desk from a browser, separated by spaces, or none (default: desk.conf)")
    ap.add_argument("--trust", default="/var/lib/desk-trust" if os.path.isdir("/var/lib/desk-trust") else os.path.join(HERE, ".trust"),
                    help="where the secure link keeps the desk's key and its owners (trust.py; default: /var/lib/desk-trust "
                    "on a board, .trust/ here elsewhere)")
    ap.add_argument("--claim", default="10.55.0.0/24", help="networks a phone may claim the desk over, both ends of the "
                    "connection inside (default: the USB cable; 127.0.0.0/8 to try it on a laptop)")
    ap.add_argument("--near", default="127.0.0.0/8,10.55.0.0/24", help="networks whose requests pass the lock as they "
                    "are, from the desk's own page (default: this device and the USB cable; SECURE-LINK.md, step 3)")
    ap.add_argument("--stt", default="~/.models/transcribe", help="sherpa-onnx and the speech model: recordings in ~/Inbox become memos in ~/Memos (see voice.py)")
    ap.add_argument("--addons", default=conf().get("addons", ""), help="add-ons to load: Python packages, separated by "
                    "spaces, that bring their own window and routes (addons.py; default: desk.conf)")
    ap.add_argument("--mesh", default=conf().get("mesh_device", "auto"), help="where Mesh finds its radio: auto, usb, serial, "
                    "/dev/ttyACM0, tcp:host, or off (default: desk.conf's mesh_device)")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8800)
    args = ap.parse_args()
    HOME = config.HOME = os.path.realpath(os.path.expanduser(args.home))
    TERMNL = os.path.realpath(os.path.expanduser(args.termnl))
    if not os.path.isfile(os.path.join(TERMNL, "termnl", "server.py")) and not stat.S_ISSOCK(os.stat(TERMNL).st_mode if os.path.exists(TERMNL) else 0):
        sys.exit("no TermNL in %s: clone it next to this folder, or pass --termnl (its folder, or its service's socket)" % TERMNL)
    os.makedirs(HOME, exist_ok=True)
    ALLOWED = config.ALLOWED = set(FORMS) if args.allow == "all" else {g for g in args.allow.split(",") if g}
    unknown = ALLOWED - set(FORMS)
    if unknown:
        sys.exit("unknown group: " + ", ".join(sorted(unknown)))
    config.TALK = Below(TERMNL) if stat.S_ISSOCK(os.stat(TERMNL).st_mode) else talk(TERMNL)
    # a companion may live under a path (GitHub Pages: https://<you>.github.io/symbios/): the browser's Origin, which
    # the desk checks, is its scheme and host only; the QR code's link opens the whole address of the first one
    # desk.conf names (the others may only call the desk)
    homes = [c.rstrip("/") for c in args.companion.split() if c != "none"]
    config.COMPANION = {"%s://%s" % (u.scheme, u.netloc) for u in map(urllib.parse.urlsplit, homes)}
    config.COMPANION_HOME = homes[0] if homes else None
    try:
        SHELL = config.SHELL = [] if args.shell == "off" else [ipaddress.ip_network(n) for n in args.shell.split(",") if n]
    except ValueError as e:
        sys.exit("--shell: " + str(e))
    try:
        config.NEAR = [ipaddress.ip_network(n) for n in args.near.split(",") if n]
    except ValueError as e:
        sys.exit("--near: " + str(e))
    try:
        config.CLAIM = [ipaddress.ip_network(n) for n in args.claim.split(",") if n]
    except ValueError as e:
        sys.exit("--claim: " + str(e))
    desktop.start(HOME)  # the home's own folders, the rulebook, the index of its files
    trust.start(args.trust)
    config.LOCAL = trust.local_pass()
    threading.Thread(target=watch_screens, daemon=True).start()
    import voice
    voice.start(os.path.realpath(os.path.expanduser(args.stt)), HOME)
    import ask
    ask.start(HOME)  # the Ask window's answers, MiniLM kept loaded beside this server
    from mesh.routes import Mesh
    MESH = Mesh(HOME, {**conf(), "mesh_device": args.mesh})  # a Meshtastic radio plugged in, any board (mesh/)
    MESH.start()
    import addons
    addons.load([a for a in args.addons.split() if a != "desk_meshtastic"], HOME, conf())  # each one's window and routes; desk_meshtastic: now mesh/
    print("desk on http://%s:%d  home %s  TermNL %s  running: %s  shell for: %s" % (
        args.host, args.port, HOME, TERMNL, ", ".join(sorted(ALLOWED)) or "nothing", ", ".join(map(str, SHELL)) or "nobody"))
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()
