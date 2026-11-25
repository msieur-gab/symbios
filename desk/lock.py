"""The lock in front of the desk (SECURE-LINK.md): the screens let in by the owner's phone (step 5), the claim
by the cable or by QR code, and their routes. trust.py holds the keys, the owners and the sealing."""
import io
import ipaddress
import os
import re
import secrets
import socket
import sys
import threading
import time
from http.cookies import SimpleCookie

import config
import signals
import trust

# ---- screens (SECURE-LINK.md, step 5): once the desk has an owner, a screen showing the desk's page (the board's own
# HDMI kiosk, a laptop on the cable or the WiFi) shows a lock screen with a code until the owner's phone allows it
# (Gab, 2026-10-27: "hdmi plug need phone approval", "wifi requires phone as well to unlock"). Allowed, it gets a pass
# (a cookie, HttpOnly, SameSite=Strict) kept here in memory, so a restart ends every pass; it is also bound to the
# screen's address. The HDMI kiosk's pass ends when the screen is unplugged, a cable laptop's when the cable comes out
# (watch_screens), a WiFi laptop's after WIFI_PASS seconds (Claude's default, changeable).
SCREENS = {}   # pass → {"id", "kind", "ip", "since", "until", "era"}; the id names it to the phone, which never sees the pass;
               # era: who owned the desk when it was allowed (trust.era): a takeover or the reset ends it
WAITING = {}   # id → {"code", "kind", "ip", "since", "state": waiting | allowed | refused, "pass"}
SCREENING = threading.Condition()
WIFI_PASS = 12 * 3600


def screen_kind(ip):
    """Where a screen asks from: the board itself is its HDMI kiosk, 10.55.0.x is the cable, the rest is the WiFi."""
    return "hdmi" if ip.startswith("127.") else "cable" if ip.startswith("10.55.0.") else "wifi"


def screen_ask(ip):
    with SCREENING:
        now = time.time()
        for old in [i for i, w in WAITING.items() if now - w["since"] > 300]:
            del WAITING[old]  # a code waits 5 minutes at most; the lock screen asks again
        while len(WAITING) >= 16:
            del WAITING[min(WAITING, key=lambda i: WAITING[i]["since"])]
        i = secrets.token_urlsafe(9)
        WAITING[i] = {"code": "%04d" % secrets.randbelow(10000), "kind": screen_kind(ip), "ip": ip, "since": now, "state": "waiting"}
        code = WAITING[i]["code"]
    # the owner's phone holds /api/changes open: told now, it shows the code at once instead of at its next look, up
    # to 15 s later (Gab, 24 Nov: "it takes a very long time for these codes to show up inside the app sheet")
    signals.publish(".lock", "screen")
    return {"id": i, "code": code}


def screen_answer(i, allow):
    with SCREENING:
        w = WAITING.get(i)
        if not w or w["state"] != "waiting":
            return False
        if allow:
            w["pass"] = secrets.token_urlsafe(24)
            SCREENS[w["pass"]] = {"id": secrets.token_urlsafe(6), "kind": w["kind"], "ip": w["ip"], "since": time.time(),
                                  "until": time.time() + WIFI_PASS if w["kind"] == "wifi" else None, "era": trust.era()}
        w["state"] = "allowed" if allow else "refused"
        SCREENING.notify_all()
        return True


def screen_of(handler):
    """The pass this request carries, if it still holds, from the address it was given to: its entry, or None."""
    try:
        got = SimpleCookie(handler.headers.get("Cookie", "")).get("desk-screen")
    except Exception:
        return None
    with SCREENING:
        p = SCREENS.get(got.value) if got else None
        if not p or p["ip"] != handler.client_address[0]:
            return None
        if (p["until"] and time.time() > p["until"]) or p["era"] != trust.era():
            del SCREENS[got.value]
            return None
        return p


def screen_pass(handler):
    """Whether this request carries a screen's pass that still holds, from the address it was given to."""
    return screen_of(handler) is not None


def screens_open():
    """The screens let in now, for the phone's Settings (the pass itself stays here)."""
    with SCREENING:
        now, era = time.time(), trust.era()
        for p in [p for p, v in SCREENS.items() if (v["until"] and now > v["until"]) or v["era"] != era]:
            del SCREENS[p]
        return [{k: v[k] for k in ("id", "kind", "ip", "since", "until")} for v in SCREENS.values()]


def screen_close(i):
    """Ends a screen's pass (the phone disconnects one let in by mistake; "all" ends every one): that screen is back
    on its lock screen at once (it waits at /api/screen/watch). How many ended."""
    with SCREENING:
        gone = [p for p, v in SCREENS.items() if i == "all" or v["id"] == i]
        for p in gone:
            del SCREENS[p]
        SCREENING.notify_all()  # the screens waiting at /api/screen/watch learn it at once
        return len(gone)


def watch_screens():
    """Ends the HDMI kiosk's passes when no screen has been plugged in for a few seconds (a projector blinks out for
    half a second when it changes mode), and a cable laptop's when the USB cable is out. Only on a board with the
    USB cable (a laptop running the desk has no such ends to watch)."""
    import glob
    if not glob.glob("/sys/class/udc/*"):
        return
    def plugged(pattern, yes):
        return any(open(f).read().strip() == yes for f in glob.glob(pattern))
    gone = {"hdmi": 0, "cable": 0}
    while True:
        time.sleep(2)
        for kind, out in (("hdmi", not plugged("/sys/class/drm/card*/card*-HDMI*/status", "connected")),
                          ("cable", not plugged("/sys/class/udc/*/state", "configured"))):
            gone[kind] = gone[kind] + 1 if out else 0
            if gone[kind] == 2:
                with SCREENING:
                    for p in [p for p, v in SCREENS.items() if v["kind"] == kind]:
                        del SCREENS[p]
                    SCREENING.notify_all()


# ---- the claim by QR code (Gab, 2026-11-23: "plug the board into a device, and here a computer, then say that the
# board is not claimed and display a QR code. Then the phone that scanned the QR code is the one that claimed the
# board"). A screen near the board (its own, or a computer on its cable) shows a code; the phone that brings it back,
# over the WiFi, becomes the owner. Seeing that screen is the proof of being next to the board, as the cable was.
# The code holds CODE_LIFE seconds and opens once; CODE_MISSES wrong ones and it is replaced ----
CODE_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: read off a screen and typed on a phone
CODE_LIFE, CODE_MISSES = 600, 5
# wrong codes are counted per address (review of 24 Nov, A4: from any address, five replaced the code, so a stranger on
# the WiFi could keep it changing and no phone could claim): an address with CODE_MISSES wrong ones is refused until the
# code changes; CODE_ALL wrong ones from every address together, and the code is replaced (31^8 codes: guessing stays out
# of reach)
CODE_ALL = 200
CODE = {"code": None, "until": 0, "misses": {}}
CODING = threading.Lock()


def claim_code():
    """The code the near screen shows: the same until it expires or is used, then a new one."""
    with CODING:
        if not CODE["code"] or time.time() > CODE["until"]:
            CODE.update(code="".join(secrets.choice(CODE_LETTERS) for _ in range(8)), until=time.time() + CODE_LIFE, misses={})
        return CODE["code"], CODE["until"]


def code_opens(given, who):
    """Whether a phone's code is the one shown: once only, then gone. Typed codes may come with a dash or spaces.
    who: the address it comes from; one that gave CODE_MISSES wrong ones is refused until the code changes."""
    given = re.sub(r"[^A-Z0-9]", "", str(given).upper())
    with CODING:
        misses = CODE["misses"]
        if misses.get(who, 0) >= CODE_MISSES:
            return False
        ok = bool(CODE["code"]) and time.time() <= CODE["until"] and secrets.compare_digest(given, CODE["code"])
        if ok:
            CODE.update(code=None, until=0, misses={})
        else:
            misses[who] = misses.get(who, 0) + 1
            if sum(misses.values()) >= CODE_ALL:
                CODE.update(code=None, until=0, misses={})  # guessed at from everywhere: the screen shows a new one
        return ok


def wifi_address():
    """The board's address on the network its default route goes through (its WiFi), or None. Nothing is sent."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if any(ipaddress.ip_address(ip) in net for net in config.NEAR) else ip


def qr_svg(text):
    """The QR code as an SVG, drawn on the board (python3-qrcode), or None without it: the page shows the code alone."""
    try:
        import qrcode
        import qrcode.image.svg
    except ImportError:
        return None
    img = qrcode.make(text, image_factory=qrcode.image.svg.SvgPathImage, border=2)
    out = io.BytesIO()
    img.save(out)  # the same in qrcode 7 (Ubuntu 22.04) and later
    return out.getvalue().decode()


def own_page(handler):
    """Whether the request comes from the desk's own page, at an address or a .local name, or from no page at all (a
    program): the Origin, when there is one, is the desk itself, and the board is named as itself. A DNS-rebinding page
    gives the board a name of its own (review of 24 Nov, A2: it read the claim code); shell.py's near() asks the same."""
    host = handler.headers.get("Host", "")
    name = host.rsplit(":", 1)[0]
    known = name == "localhost" or name.endswith(".local") or re.fullmatch(r"[\d.]+", name)
    return bool(known) and handler.headers.get("Origin") in (None, "http://" + host)


# ---- releasing the desk (Gab, 24 Nov: "unclaim a board from plugging the board in a computer, unlocking it via the
# phone, because we have this security code that locks it, and then release it from there"; decided: "we just keep the
# owner, you release the cable on your phone, making instant connection, and all the files are kept. If it's not the
# case, that means you have been hacked, then flash the card"). A screen let in, on the cable or the board's own,
# asks; the owner's phone confirms, sealed; then the desk has no owner, its files kept, and shows the QR card again.
# A screen alone never frees the desk: whoever got past its lock could then claim it. One request waits at a time ----
RELEASES = {}  # id → {"kind", "ip", "since", "state": waiting | released | refused}
RELEASE_LIFE = 300


def release_ask(screen):
    with SCREENING:
        RELEASES.clear()  # one at a time: a new ask replaces the one before
        i = secrets.token_urlsafe(9)
        RELEASES[i] = {"kind": screen["kind"], "ip": screen["ip"], "since": time.time(), "state": "waiting"}
        SCREENING.notify_all()
    signals.publish(".lock", "release")  # the phone asks at once, as for a screen's code
    return i


def releases_waiting():
    with SCREENING:
        now = time.time()
        for old in [i for i, r in RELEASES.items() if now - r["since"] > RELEASE_LIFE]:
            del RELEASES[old]
        return {i: r for i, r in RELEASES.items() if r["state"] == "waiting"}


def release_answer(i, release):
    """The phone's answer: True if it was a request waiting. Released, the desk has no owner (trust.unclaim: no owner,
    no word, no session; the files stay) and every screen's pass ends."""
    with SCREENING:
        r = releases_waiting().get(i)
        if not r:
            return False
        r["state"] = "released" if release else "refused"
        if release:
            trust.unclaim()
            SCREENS.clear()
        SCREENING.notify_all()
        return True


class LockRoutes:
    """The server's routes for the lock: the screens, the claim, the phone's session (mixed into its handler).
    lock_get and lock_post answer a route of theirs and say True, or leave it to the server and say False."""

    def nearby(self):
        """The board's own screen or the USB cable (--near), from the desk's own page: these pass the lock as they
        are until the phone unlocks screens (SECURE-LINK.md, step 5). Another site open in the same browser doesn't."""
        try:
            who = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return False
        return any(who in net for net in config.NEAR) and own_page(self)

    def lock_get(self, path, q):
        if path == "/api/screen":  # the lock screen asks first: is this screen let in?
            # the same rule as gate(): before the claim only the board's own screen and the cable get in, so a
            # screen on the WiFi is told so instead of loading a desk whose every request is refused (31 Oct, the
            # new board seen over the WiFi before any claim: the page reloaded about once a second)
            claimed = trust.claimed()
            self.send({"claimed": claimed, "allowed": screen_pass(self) if claimed else self.nearby()})
        elif path == "/api/screen/wait":  # until the owner's phone answers (25 s at most, then ask again)
            with SCREENING:
                w = WAITING.get(q.get("id", ""))
                if w and w["state"] == "waiting":
                    SCREENING.wait_for(lambda: w["state"] != "waiting", timeout=25)
            if not w or w["ip"] != self.client_address[0]:
                self.send({"state": "gone"})
            elif w["state"] != "allowed":
                self.send({"state": w["state"]})
            else:
                with SCREENING:  # the pass is handed once: the code is spent
                    spent = WAITING.pop(q["id"], None) is None
                if spent:
                    self.send({"state": "gone"})
                else:
                    age = "; Max-Age=%d" % WIFI_PASS if w["kind"] == "wifi" else ""
                    self.send({"state": "allowed"}, cookie="desk-screen=%s; Path=/; HttpOnly; SameSite=Strict%s" % (w["pass"], age))
        elif path == "/api/screen/watch":  # a screen let in waits here (10 s at most) until its pass ends: disconnected
            # by the phone, its own Lock, unplugged; or, before the claim, until the desk gets an owner
            claimed = trust.claimed()
            with SCREENING:  # a Condition's lock is re-entrant: screen_pass may take it again inside
                # 10 s: a screen whose board vanished (unplugged, the cable its power) learns it within ~15 s (gate.js)
                SCREENING.wait_for(lambda: trust.claimed() != claimed or (claimed and not screen_pass(self)), timeout=10)
            # the same rule as gate(): before the claim only the board's own screen and the cable get in
            claimed = trust.claimed()
            self.send({"claimed": claimed, "allowed": screen_pass(self) if claimed else self.nearby()})
        elif path == "/api/trust/code":  # the near screen's claim code, as a QR code for the phone (locked: near only)
            if trust.claimed():
                self.fail(409, "this desk has an owner")
                return True
            code, until = claim_code()
            at = wifi_address()
            port = self.server.server_address[1]
            at = at and at + ("" if port == 80 else ":%d" % port)
            link = None
            if config.COMPANION_HOME and at:
                link = config.COMPANION_HOME + "/#" + "&".join("%s=%s" % kv for kv in
                    (("claim", code), ("desk", at), ("board", trust.key_id(trust.unb64(trust.board_key())))))
            import wifi  # the network's name, so the card can say which WiFi the phone must be on (Gab, 23 Nov)
            self.send({"code": code, "left": max(0, int(until - time.time())), "desk": at, "link": link,
                       "qr": qr_svg(link) if link else None, "wifi": wifi.status().get("ssid") if at else None})
        elif path == "/api/trust/owner":  # a screen let in: who owns the desk, for Settings' This board
            if not trust.claimed():
                self.fail(409, "this desk has no owner")
                return True
            screen = screen_of(self)
            owner = next(iter(trust.OWNERS.values()), {})
            self.send({"name": owner.get("name", ""), "since": owner.get("added"), "here": screen["kind"] if screen else None,
                       "release": bool(screen) and screen["kind"] in ("cable", "hdmi")})
        elif path == "/api/trust/release/wait":  # the screen that asked waits for the phone (25 s at most, then again)
            with SCREENING:
                r = RELEASES.get(q.get("id", ""))
                if r and r["state"] == "waiting":
                    SCREENING.wait_for(lambda: r["state"] != "waiting", timeout=25)
            self.send({"state": r["state"] if r and r["ip"] == self.client_address[0] else "gone"})
        elif path == "/api/trust/release/pending":  # the owner's phone, sealed only: a screen asking to release the desk
            if not self.sid:
                self.fail(403, "only the owner's phone sees a release asked")
                return True
            self.send({"releases": [{"id": i, "kind": r["kind"], "ip": r["ip"]} for i, r in releases_waiting().items()]})
        elif path == "/api/screen/open":  # the owner's phone: the screens let in now, to disconnect one
            self.send({"screens": screens_open()}) if self.sid else self.fail(403, "only the owner's phone sees the screens")
        elif path == "/api/screen/pending":  # the owner's phone, sealed only: the screens waiting for it
            if not self.sid:
                self.fail(403, "only the owner's phone sees the screens waiting")
                return True
            with SCREENING:
                self.send({"screens": [{"id": i, "code": w["code"], "kind": w["kind"], "ip": w["ip"]}
                                       for i, w in WAITING.items() if w["state"] == "waiting" and time.time() - w["since"] < 300]})
        else:
            return False
        return True

    def lock_post_plain(self, route):
        """The lock's routes that take no JSON body."""
        if route == "/api/trust/ping":
            self.ping()
        elif route == "/api/screen/ask":  # a lock screen asks for a code
            self.send(screen_ask(self.client_address[0]))
        elif route == "/api/trust/release":  # a screen let in, on the cable or the board's own, asks to release the desk
            screen = screen_of(self)
            if self.sid or not screen or screen["kind"] not in ("cable", "hdmi") or not trust.claimed():
                self.fail(403, "the desk is released from a screen on its cable or its own, then confirmed on the owner's phone")
                return True
            self.send({"id": release_ask(screen)})
        elif route == "/api/screen/lock":  # the desk's own Lock button: this screen ends its pass, like locking a computer
            got = SimpleCookie(self.headers.get("Cookie", "")).get("desk-screen")
            with SCREENING:
                done = bool(got) and SCREENS.pop(got.value, None) is not None
                SCREENING.notify_all()
            self.send({"done": done}, cookie="desk-screen=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
        else:
            return False
        return True

    def lock_post(self, route, body):
        """The lock's routes that take a JSON body."""
        if route == "/api/screen/close":  # only the owner's phone, sealed: disconnects a screen ({"id": …}, or "all")
            if not self.sid:
                self.fail(403, "only the owner's phone disconnects a screen")
                return True
            try:
                self.send({"closed": screen_close(str(body["id"]))})
            except (KeyError, TypeError):
                self.fail(400, "expected {\"id\": \"…\"}")
        elif route == "/api/screen/answer":  # only the owner's phone, sealed: an allowed screen can't let in another
            if not self.sid:
                self.fail(403, "only the owner's phone answers a screen")
                return True
            try:
                self.send({"done": screen_answer(str(body["id"]), bool(body["allow"]))})
            except (KeyError, TypeError):
                self.fail(400, "expected {\"id\": \"…\", \"allow\": true}")
        elif route == "/api/trust/release/answer":  # only the owner's phone, sealed: {"id": …, "release": true}
            if not self.sid:
                self.fail(403, "only the owner's phone releases the desk")
                return True
            try:
                i, release = str(body["id"]), bool(body["release"])
            except (KeyError, TypeError):
                return self.fail(400, "expected {\"id\": \"…\", \"release\": true}") or True
            if i not in releases_waiting():
                self.send({"done": False})
                return True
            # the answer first, sealed with the session the release then ends
            self.send({"done": True, "released": release})
            release_answer(i, release)
            sys.stderr.write("trust: %s from %s\n" % ("released" if release else "release refused", self.client_address[0]))
        elif route == "/api/trust/claim":
            self.claim(body)
        elif route == "/api/trust/word":  # the owner's phone sets or changes the secret word, sealed only
            if not self.sid:
                self.fail(403, "only the owner's phone sets the secret word")
                return True
            try:
                trust.set_word(body.get("word") if isinstance(body, dict) else None)
            except trust.Refused as e:
                self.fail(400, str(e))
                return True
            self.send({"done": True})
        elif route == "/api/trust/session":
            try:
                self.send(trust.begin(str(body["id"]), str(body["key"])))
            except (KeyError, TypeError, ValueError):
                self.fail(400, "expected {\"id\": \"…\", \"key\": \"…\"}")
            except trust.Refused as e:
                sys.stderr.write("trust: session refused: %s (phone %s)\n" % (e, str(body.get("id"))[:16]))
                self.fail(403, "refused")
        else:
            return False
        return True

    def claim(self, body):
        """The first phone becomes the desk's owner (trust.py), over the cable: both ends of the
        connection on a network --claim names, so a request over the WiFi never claims by itself, whatever its
        sender says it is; or over the WiFi with the code a near screen shows ("code": the claim by QR code). Refused once the desk has an owner, unless the phone gives the secret word ("word"):
        then it takes the desk over (SECURE-LINK.md, step 6). The word comes plain, over the cable only."""
        # only from the companion, the desk's own page, or a program (no Origin), and only as JSON, so a browser asks the
        # desk first: any other site open in the computer's browser on the cable could claim a fresh desk with a plain
        # form-style request (review of 24 Nov, A1)
        origin = self.headers.get("Origin")
        if not (origin in config.COMPANION or own_page(self)) or \
                not self.headers.get("Content-Type", "").split(";")[0].strip().lower() == "application/json":
            sys.stderr.write("trust: claim refused: from a page the desk doesn't expect (%s)\n" % origin)
            return self.fail(403, "the claim comes from the companion")
        try:
            ends = [ipaddress.ip_address(self.client_address[0]), ipaddress.ip_address(self.connection.getsockname()[0])]
        except ValueError:
            ends = []
        word = body.get("word") if isinstance(body, dict) else None
        cabled = bool(ends) and any(all(e in net for e in ends) for net in config.CLAIM)
        # or over the WiFi, with the code a near screen shows (the claim by QR code); a takeover stays on the cable
        coded = not cabled and word is None and isinstance(body, dict) and "code" in body and not trust.claimed()
        if coded and not code_opens(body["code"], self.client_address[0]):
            sys.stderr.write("trust: claim refused: wrong code from %s\n" % self.client_address[0])
            return self.fail(403, "wrong code")
        if not cabled and not coded:
            return self.fail(403, "the claim is made over the USB cable, or with the code a screen near the desk shows")
        try:
            got = trust.claim(str(body["key"]), str(body.get("name", "")), None if word is None else str(word))
        except (KeyError, TypeError, ValueError):
            return self.fail(400, "expected {\"key\": \"…\"}")
        except trust.Refused as e:
            why = str(e)
            sys.stderr.write("trust: claim refused: %s\n" % why)
            if why.startswith("wait ") or "(wait " in why:
                left = trust.wait_left()
                return self.send({"error": "too many wrong words: wait %d min" % max(1, round(left / 60)), "wait": left}, code=429)
            return self.fail(403 if why.startswith("wrong word") else 409 if trust.claimed() else 400, why.split(" (")[0])
        sys.stderr.write("trust: %s by %s\n" % ("taken over" if word is not None else "claimed", got["id"]))
        with SCREENING:  # the screens waiting at /api/screen/watch: a new owner locks them
            SCREENING.notify_all()
        self.send({**got, "host": os.uname().nodename})

    def ping(self):
        """A sealed hello (opened by gate, its answer sealed by send): proves the phone and the desk worked out the
        same session keys."""
        if not self.sid:
            return self.fail(403, "expected a sealed message")
        owner = trust.OWNERS.get(trust.owner_of(self.sid), {})
        self.send({"pong": True, "host": os.uname().nodename, "since": owner.get("added")})
