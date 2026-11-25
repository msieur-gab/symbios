"""Releasing the desk (lock.py; Gab, 24 Nov: "unclaim a board from plugging the board in a computer, unlocking it via
the phone ... and then release it from there"), and the claim's fixes of the review of 24 Nov (symbios SECURITY.md: A1
the claim only from the companion, as JSON; A2 the claim code never to a rebinding page; A4 wrong codes per address),
against a running desk with no owner, a phone played as in gate_test.py:

    python3 server.py --home /tmp/rel-home --trust /tmp/rel-trust --claim 127.0.0.0/8 --port 8877 --mesh off
    python3 bench/release_test.py 127.0.0.1:8877 192.168.1.51:8877   # nearby (the board's own screen), the WiFi
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trust  # noqa: E402  (its helpers only: b64, the nonce, what a message is bound to)
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402

NEAR, WIFI = sys.argv[1], sys.argv[2]


def call(at, method, path, body=b"", headers=None, timeout=10):
    r = urllib.request.Request("http://" + at + path, data=body if method == "POST" else None, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as got:
            return got.status, got.read(), got.headers
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers


def post_json(at, path, data):
    status, body, _ = call(at, "POST", path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    return status, json.loads(body or b"{}")


class Phone:
    def __init__(self):
        self.key = ec.generate_private_key(trust.CURVE)
        self.public = trust.raw(self.key.public_key())

    def claim(self, at):
        status, got = post_json(at, "/api/trust/claim", {"key": trust.b64(self.public), "name": "gate test"})
        assert status == 200, (status, got)
        self.id, self.board = got["id"], trust.unb64(got["board"])

    def session(self, at):
        once = ec.generate_private_key(trust.CURVE)
        status, got = post_json(at, "/api/trust/session", {"id": self.id, "key": trust.b64(trust.raw(once.public_key()))})
        assert status == 200, (status, got)
        theirs = trust.unb64(got["key"])
        both = self.key.exchange(ec.ECDH(), trust.point(self.board)) + once.exchange(ec.ECDH(), trust.point(theirs))
        keys = HKDF(hashes.SHA256(), 64, trust.raw(once.public_key()) + theirs, trust.INFO).derive(both)
        return Session(at, got["session"], keys)


class Session:
    def __init__(self, at, sid, keys):
        self.at, self.sid, self.up, self.down, self.n = at, sid, AESGCM(keys[:32]), AESGCM(keys[32:]), 0

    def sealed(self, method, path, text, bound_path=None):
        """(n, sealed bytes) for a request; bound_path seals it for another path than the one it is sent to."""
        self.n += 1
        return self.n, self.up.encrypt(trust.nonce(self.n), text, trust.bound(self.sid, method + " " + (bound_path or path), "up"))

    def send(self, method, path, n, sealed):
        seal = {"X-Seal": trust.b64(sealed)} if method == "GET" else {"Content-Type": "application/octet-stream"}
        return call(self.at, method, path, sealed, {"X-Session": self.sid, "X-N": str(n), **seal})

    def opened(self, method, path, status, body, headers):
        assert status == 200, (status, body)
        return json.loads(self.down.decrypt(trust.nonce(int(headers["X-N"])), body, trust.bound(self.sid, method + " " + path, "down")))



results = []


def check(name, ok):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name)


def claim_json(at, data, headers):
    status, body, _ = call(at, "POST", "/api/trust/claim", json.dumps(data).encode(), headers)
    return status, json.loads(body or b"{}")


hello = json.loads(call(NEAR, "GET", "/api/hello")[1])
COMPANION = hello["companion"][0]
assert not hello["claimed"], "run it against a desk with no owner"
me = Phone()
KEY = {"key": trust.b64(me.public), "name": "release test"}

# ---- A1: the claim only from the companion, the desk's own page or a program, and only as JSON
status, _ = claim_json(NEAR, KEY, {"Content-Type": "text/plain", "Origin": "https://evil.example"})
check("another site can't claim the desk with a plain form-style request over the cable", status == 403)
status, _ = claim_json(NEAR, KEY, {"Content-Type": "application/json", "Origin": "https://evil.example"})
check("another site can't claim it as JSON either", status == 403)
status, _ = claim_json(NEAR, KEY, {"Content-Type": "text/plain"})
check("a claim that isn't JSON is refused, even from no page", status == 403)
check("still no owner", json.loads(call(NEAR, "GET", "/api/hello")[1])["claimed"] is False)

# ---- A2: the claim code only to the desk's own page, never to a page that renamed the board (DNS rebinding)
status, _, _ = call(NEAR, "GET", "/api/trust/code", headers={"Host": "evil.example", "Origin": "http://evil.example"})
check("a rebinding page near the board doesn't get the claim code", status == 403)
status, body, _ = call(NEAR, "GET", "/api/trust/code")
code = json.loads(body)["code"]
check("the desk's own page near the board gets it", status == 200 and len(code) == 8)

# ---- A4: wrong codes counted per address
for _ in range(5):
    status, got = claim_json(WIFI, {**KEY, "code": "AAAAAAAA"}, {"Content-Type": "application/json", "Origin": COMPANION})
check("a wrong code over the WiFi is refused", status == 403 and got.get("error") == "wrong code")
status, got = claim_json(WIFI, {**KEY, "code": code}, {"Content-Type": "application/json", "Origin": COMPANION})
check("after five wrong ones, that address is refused even the right code", status == 403)
check("and the code shown near the board hasn't changed for everyone else",
      json.loads(call(NEAR, "GET", "/api/trust/code")[1])["code"] == code)

# the owner: over the cable, from the companion
status, got = claim_json(NEAR, KEY, {"Content-Type": "application/json", "Origin": COMPANION})
check("the companion claims it over the cable", status == 200)
me.id, me.board = got["id"], trust.unb64(got["board"])
s = me.session(WIFI)


def sealed(method, path, data=None):
    n, box = s.sealed(method, path, b"" if data is None else json.dumps(data).encode())
    status, body, headers = s.send(method, path, n, box)
    return s.opened(method, path, status, body, headers) if status == 200 else status


def screen(at):
    """A screen at this address let in by the phone: its pass (the cookie)."""
    ask = json.loads(call(at, "POST", "/api/screen/ask")[1])
    sealed("POST", "/api/screen/answer", {"id": ask["id"], "allow": True})
    return call(at, "GET", "/api/screen/wait?id=" + ask["id"])[2]["Set-Cookie"].split(";")[0]


drop = "/api/inbox?name=release-test.txt&modified=1&source=share"
kept = sealed("POST", drop)
check("a file of the owner's, before the release", isinstance(kept, dict) and "path" in kept)
status, _, _ = call(NEAR, "GET", "/api/screen/pending")
check("the screens waiting can't be read plainly near the board either", status == 403)

before = sealed("GET", "/api/changes?after=-1&boot=0")
near, far = screen(NEAR), screen(WIFI)
told = sealed("GET", "/api/changes?after=%d&boot=%d" % (before["seq"], before["boot"]))
check("a screen asking for a code is told to the phone's /api/changes at once (\".lock\")",
      any(c["folder"] == ".lock" and c["name"] == "screen" for c in told["changes"]))
status, body, _ = call(NEAR, "GET", "/api/trust/owner", headers={"Cookie": near})
o = json.loads(body)
check("This board: the board's own screen sees its owner, and may ask to release it", status == 200 and o["name"] == "release test" and o["release"] is True)
o = json.loads(call(WIFI, "GET", "/api/trust/owner", headers={"Cookie": far})[1])
check("a screen on the WiFi sees its owner, but may not release it", o["release"] is False)
status, _, _ = call(NEAR, "POST", "/api/trust/release")
check("no release asked without a screen's pass", status == 403)
status, _, _ = call(WIFI, "POST", "/api/trust/release", headers={"Cookie": far})
check("no release asked from a screen on the WiFi", status == 403)

# asked, then refused
status, body, _ = call(NEAR, "POST", "/api/trust/release", headers={"Cookie": near})
first = json.loads(body)["id"]
check("the board's own screen asks to release it", status == 200)
told = sealed("GET", "/api/changes?after=%d&boot=%d" % (told["seq"], told["boot"]))
check("and the phone is told at once", any(c["folder"] == ".lock" and c["name"] == "release" for c in told["changes"]))
status, _, _ = call(NEAR, "GET", "/api/trust/release/pending", headers={"Cookie": near})
check("the screen can't see the release asked: only the phone", status == 403)
status, _, _ = call(NEAR, "POST", "/api/trust/release/answer", json.dumps({"id": first, "release": True}).encode(),
                    {"Content-Type": "application/json", "Cookie": near})
check("the screen can't confirm its own release", status == 403)
got = sealed("GET", "/api/trust/release/pending")
check("the owner's phone sees it, from the board's own screen", got == {"releases": [{"id": first, "kind": "hdmi", "ip": NEAR.split(":")[0]}]})
check("the phone refuses it", sealed("POST", "/api/trust/release/answer", {"id": first, "release": False}) == {"done": True, "released": False})
check("the screen is told", json.loads(call(NEAR, "GET", "/api/trust/release/wait?id=" + first, headers={"Cookie": near})[1]) == {"state": "refused"})
check("refused, the desk keeps its owner", json.loads(call(NEAR, "GET", "/api/hello")[1])["claimed"] is True)

# asked again, an old answer is spent, then released
first = json.loads(call(NEAR, "POST", "/api/trust/release", headers={"Cookie": near})[1])["id"]
second = json.loads(call(NEAR, "POST", "/api/trust/release", headers={"Cookie": near})[1])["id"]
check("one release waits at a time: an answer to the older one does nothing",
      sealed("POST", "/api/trust/release/answer", {"id": first, "release": True}) == {"done": False}
      and json.loads(call(NEAR, "GET", "/api/hello")[1])["claimed"] is True)
# a sealed request waiting on the desk while it is released (the phone's /api/changes): told the session is gone, not
# cut off (seen on the Orange Pi, 24 Nov: the answer had no session left to be sealed with, and the server raised)
import threading  # noqa: E402
now = sealed("GET", "/api/changes?after=-1&boot=0")  # after the last ask: nothing else will wake it
waiter = {}
path = "/api/changes?after=%d&boot=%d" % (now["seq"], now["boot"])
n_, box_ = s.sealed("GET", path, b"")
def wait():
    # /api/changes waits up to 25 s for news: a longer wait than the other calls'
    waiter["status"] = call(s.at, "GET", path, b"", {"X-Session": s.sid, "X-N": str(n_), "X-Seal": trust.b64(box_)}, timeout=40)[0]
waiting = threading.Thread(target=wait)
waiting.start()

check("the owner's phone confirms the release, its answer sealed", sealed("POST", "/api/trust/release/answer", {"id": second, "release": True}) == {"done": True, "released": True})
hello = json.loads(call(NEAR, "GET", "/api/hello")[1])
check("released: no owner, no secret word", hello["claimed"] is False and hello["word"] is False)
check("the screen that asked is told", json.loads(call(NEAR, "GET", "/api/trust/release/wait?id=" + second)[1]) == {"state": "released"})
check("the phone's session has ended", sealed("GET", "/api/status") in (401, 403))
waiting.join(45)
check("a sealed request that was waiting is told its session is gone (401), not cut off", waiter.get("status") == 401)
status, _, _ = call(WIFI, "GET", "/api/status", headers={"Cookie": far})
check("every screen's pass has ended", status == 403)
check("near the board, the screen is let in as before a claim, to show the QR card",
      json.loads(call(NEAR, "GET", "/api/screen")[1]) == {"claimed": False, "allowed": True})
status, body, _ = call(NEAR, "GET", "/api/fs/raw?path=" + urllib.parse.quote(os.path.join(kept["went"], os.path.basename(kept["path"]))))
check("the files are kept", status == 200 and body == b"")
status, body, _ = call(NEAR, "GET", "/api/trust/code")
check("the claim code again, to be claimed again", status == 200 and len(json.loads(body)["code"]) == 8)
status, _, _ = call(NEAR, "POST", "/api/trust/release", headers={"Cookie": near})
check("no release on a desk with no owner", status == 403)

print("\n%d of %d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
