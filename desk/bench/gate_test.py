"""The lock in front of the desk's routes (server.py, gate; SECURE-LINK.md, step 3), against a running desk, with a phone
played over HTTP as the companion's trust.js does it. Run the desk with a throwaway home and keys, then this:

    python3 server.py --home /tmp/gate-home --trust /tmp/gate-trust --claim 127.0.0.0/8 --port 8876
    python3 bench/gate_test.py 127.0.0.1:8876 192.168.1.51:8876 /tmp/gate-trust   # nearby, the laptop's WiFi address, the keys

The WiFi address makes the desk see a request from the WiFi, as from a phone or a stranger on the same network. From
127.0.0.1 the desk sees its own HDMI screen (step 5: screens unlocked by the phone).
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

NEAR, WIFI, KEYS = sys.argv[1], sys.argv[2], sys.argv[3]


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


status, hello, _ = call(NEAR, "GET", "/api/hello")
hello = json.loads(hello)
check("/api/hello lists the few open routes, every other is locked", set(hello["open"]) == {"GET /api/hello", "POST /api/trust/claim", "POST /api/trust/session", "GET /api/screen", "POST /api/screen/ask", "GET /api/screen/wait"})
drop = "/api/inbox?name=gate-test.txt&modified=1&source=share"
status, body, _ = call(NEAR, "POST", drop.replace("gate-test", "gate-first"), b"before the claim")
check("before the claim, a plain drop from nearby passes (the board's screen, the cable)", status == 200)
status, body, _ = call(NEAR, "GET", "/api/screen")
check("before the claim, a screen is let in as it is", json.loads(body)["allowed"] is True)
me = Phone()
me.claim(NEAR)

status, body, _ = call(WIFI, "POST", drop, b"from a stranger")
check("a plain drop over the WiFi is refused", status == 403)
status, body, _ = call(NEAR, "POST", drop.replace("gate-test", "gate-near"), b"from the cable")
check("once claimed, a plain drop from nearby is refused too, until the phone allows that screen", status == 403)
status, body, _ = call(WIFI, "GET", "/api/status")
check("reading the board's numbers plainly over the WiFi is refused", status == 403)
for path in ("/api/articles", "/api/fs/list", "/api/slides", "/api/music"):
    status, body, _ = call(WIFI, "GET", path)
    if status != 403:
        break
check("reading articles, files, decks and music plainly over the WiFi is refused", status == 403)
status, body, _ = call(WIFI, "GET", "/")
check("the desk's page itself (its code) still loads over the WiFi", status == 200 and b"<" in body)
status, body, _ = call(WIFI, "GET", "/api/made-up-later")
check("a route nobody listed is locked from the start", status == 403)

s = me.session(WIFI)
n, sealed = s.sealed("POST", drop, b"from the owner's phone")
status, body, headers = s.send("POST", drop, n, sealed)
kept = s.opened("POST", drop, status, body, headers)
check("a sealed drop over the WiFi is kept, its answer sealed", status == 200 and "went" in kept)
raw = "/api/fs/raw?path=" + urllib.parse.quote(os.path.join(kept["went"], os.path.basename(kept["path"])))
n, sealed = s.sealed("GET", raw, b"")
status, body, headers = s.send("GET", raw, n, sealed)
check("the owner reads a file sealed, its bytes as they were sent", status == 200 and s.down.decrypt(trust.nonce(int(headers["X-N"])), body, trust.bound(s.sid, "GET " + raw, "down")) == b"from the owner's phone")
n, sealed = s.sealed("GET", "/api/status", b"")
status, body, headers = s.send("GET", "/api/status", n, sealed)
check("the owner reads the board's numbers sealed", "error" not in s.opened("GET", "/api/status", status, body, headers))
status, body, _ = s.send("POST", drop, n, sealed)
check("the same sealed drop sent again is refused", status == 403)
renamed = drop.replace("gate-test", "renamed")
n, sealed = s.sealed("POST", drop, b"renamed on the way")
status, body, _ = s.send("POST", renamed, n, sealed)
check("a sealed drop whose name was changed on the way is refused", status == 403)
status, body, _ = call(WIFI, "POST", drop, b"x" * 32, {"X-Session": "made-up", "X-N": "1"})
check("an unknown session says so (401), so the phone opens a new one", status == 401)
path = "/api/articles"
n, sealed = s.sealed("POST", path, json.dumps({"url": "not a link"}).encode())
status, body, _ = s.send("POST", path, n, sealed)
check("a refusal of a sealed request comes back plain and readable", status >= 400 and "error" in json.loads(body))
say = json.dumps({"text": "hello", "session": "gate-test"}).encode()
status, body, _ = call(WIFI, "POST", "/api/say", say, {"Content-Type": "application/json"})
check("TermNL refuses a plain sentence over the WiFi", status == 403)
status, body, _ = call(WIFI, "POST", "/api/exec", json.dumps({"command": "uptime"}).encode(), {"Content-Type": "application/json"})
check("a plain command over the WiFi is refused", status == 403)
n, sealed = s.sealed("POST", "/api/say", say)
status, body, headers = s.send("POST", "/api/say", n, sealed)
check("TermNL answers the owner's sealed sentence over the WiFi", "error" not in s.opened("POST", "/api/say", status, body, headers))
status, body, _ = call(WIFI, "GET", "/api/wifi")
check("where the board's WiFi is can't be read plainly over the WiFi any more", status == 403)
n, sealed = s.sealed("GET", "/api/wifi", b"")
status, body, headers = s.send("GET", "/api/wifi", n, sealed)
check("the owner's sealed request gets past the lock to the WiFi screen's own rule", status in (200, 501) or (status == 403 and b"locked" not in body))
n, sealed = s.sealed("POST", "/api/trust/ping", b"")
status, body, headers = s.send("POST", "/api/trust/ping", n, sealed)
check("the sealed hello still answers", s.opened("POST", "/api/trust/ping", status, body, headers).get("pong") is True)

# ---- screens unlocked by the phone (step 5)
status, body, _ = call(NEAR, "GET", "/api/screen")
check("once claimed, the board's screen isn't let in", json.loads(body) == {"claimed": True, "allowed": False})
status, body, _ = call(NEAR, "POST", "/api/screen/ask")
ask = json.loads(body)
check("the lock screen gets a 4-digit code", status == 200 and len(ask["code"]) == 4 and ask["code"].isdigit())
status, body, _ = call(WIFI, "GET", "/api/screen/pending")
check("the waiting screens can't be read plainly", status == 403)
n, sealed = s.sealed("GET", "/api/screen/pending", b"")
status, body, headers = s.send("GET", "/api/screen/pending", n, sealed)
waiting = s.opened("GET", "/api/screen/pending", status, body, headers)["screens"]
check("the owner's phone sees the code, from the board's HDMI screen", [(w["id"], w["code"], w["kind"]) for w in waiting] == [(ask["id"], ask["code"], "hdmi")])
answer = json.dumps({"id": ask["id"], "allow": True}).encode()
status, body, _ = call(NEAR, "POST", "/api/screen/answer", answer, {"Content-Type": "application/json"})
check("a screen can't allow itself", status == 403)
n, sealed = s.sealed("POST", "/api/screen/answer", answer)
status, body, headers = s.send("POST", "/api/screen/answer", n, sealed)
check("the owner's phone allows it, sealed", s.opened("POST", "/api/screen/answer", status, body, headers) == {"done": True})
status, body, _ = call(WIFI, "GET", "/api/screen/wait?id=" + ask["id"])
check("someone else waiting on that code gets nothing", json.loads(body) == {"state": "gone"})
status, body, headers = call(NEAR, "GET", "/api/screen/wait?id=" + ask["id"])
cookie = (headers.get("Set-Cookie") or "").split(";")[0]
check("the lock screen gets its pass, as a cookie the page's code can't read", json.loads(body) == {"state": "allowed"} and cookie.startswith("desk-screen=") and "HttpOnly" in headers["Set-Cookie"])
status, body, headers = call(NEAR, "GET", "/api/screen/wait?id=" + ask["id"])
check("the pass is handed once: the code is spent", json.loads(body) == {"state": "gone"} and not headers.get("Set-Cookie"))
status, body, _ = call(NEAR, "POST", drop.replace("gate-test", "gate-near"), b"from the allowed screen", {"Cookie": cookie})
check("the allowed screen drops plainly", status == 200)
status, body, _ = call(NEAR, "POST", "/api/say", say, {"Content-Type": "application/json", "Cookie": cookie})
check("TermNL answers the allowed screen", status == 200 and "error" not in json.loads(body))
status, body, _ = call(WIFI, "GET", "/api/status", headers={"Cookie": cookie})
check("the same pass from another address is refused", status == 403)
status, body, _ = call(NEAR, "GET", "/api/screen/open", headers={"Cookie": cookie})
check("an allowed screen can't list the open screens", status == 403)
n, sealed = s.sealed("GET", "/api/screen/open", b"")
status, body, headers = s.send("GET", "/api/screen/open", n, sealed)
opened = s.opened("GET", "/api/screen/open", status, body, headers)["screens"]
check("the owner's phone lists the open screens, without their passes", [w["kind"] for w in opened] == ["hdmi"] and cookie.split("=", 1)[1] not in json.dumps(opened))
close = json.dumps({"id": opened[0]["id"]}).encode()
status, body, _ = call(NEAR, "POST", "/api/screen/close", close, {"Content-Type": "application/json", "Cookie": cookie})
check("a screen can't disconnect screens", status == 403)
import threading  # noqa: E402
import time  # noqa: E402
watched = {}
def watch():
    t0 = time.time()
    watched["got"] = json.loads(call(NEAR, "GET", "/api/screen/watch", headers={"Cookie": cookie}, timeout=30)[1])
    watched["after"] = time.time() - t0
waiting = threading.Thread(target=watch)
waiting.start()
time.sleep(1)
n, sealed = s.sealed("POST", "/api/screen/close", close)
status, body, headers = s.send("POST", "/api/screen/close", n, sealed)
check("the owner's phone disconnects it", s.opened("POST", "/api/screen/close", status, body, headers) == {"closed": 1})
waiting.join()
check("the screen waiting on the desk is told at once", watched["got"]["allowed"] is False and watched["after"] < 2)
status, body, _ = call(NEAR, "GET", "/api/status", headers={"Cookie": cookie})
gone = json.loads(call(NEAR, "GET", "/api/screen", headers={"Cookie": cookie})[1])
check("disconnected, the screen is locked again", status == 403 and gone["allowed"] is False)
ask = json.loads(call(NEAR, "POST", "/api/screen/ask")[1])
answer = json.dumps({"id": ask["id"], "allow": True}).encode()
n, sealed = s.sealed("POST", "/api/screen/answer", answer)
s.send("POST", "/api/screen/answer", n, sealed)
status, body, headers = call(NEAR, "GET", "/api/screen/wait?id=" + ask["id"])
cookie = headers["Set-Cookie"].split(";")[0]
status, body, headers = call(NEAR, "POST", "/api/screen/lock", b"", {"Cookie": cookie})
check("the desk's Lock button ends its own pass, and clears the cookie", json.loads(body) == {"done": True} and "Max-Age=0" in headers["Set-Cookie"])
status, body, _ = call(NEAR, "GET", "/api/status", headers={"Cookie": cookie})
check("locked, the screen is refused", status == 403)
ask = json.loads(call(NEAR, "POST", "/api/screen/ask")[1])
answer = json.dumps({"id": ask["id"], "allow": True}).encode()
n, sealed = s.sealed("POST", "/api/screen/answer", answer)
s.send("POST", "/api/screen/answer", n, sealed)
cookie = call(NEAR, "GET", "/api/screen/wait?id=" + ask["id"])[2]["Set-Cookie"].split(";")[0]
status, body, _ = call(NEAR, "GET", "/api/status", headers={"Cookie": "desk-screen=made-up"})
check("a made-up pass is refused", status == 403)
status, body, _ = call(WIFI, "POST", "/api/screen/ask")
other = json.loads(body)
n, sealed = s.sealed("GET", "/api/screen/pending", b"")
status, body, headers = s.send("GET", "/api/screen/pending", n, sealed)
check("a screen on the WiFi shows as such on the phone", [w["kind"] for w in s.opened("GET", "/api/screen/pending", status, body, headers)["screens"]] == ["wifi"])
answer = json.dumps({"id": other["id"], "allow": False}).encode()
n, sealed = s.sealed("POST", "/api/screen/answer", answer)
s.send("POST", "/api/screen/answer", n, sealed)
status, body, headers = call(WIFI, "GET", "/api/screen/wait?id=" + other["id"])
check("a refused screen is told, and gets no pass", json.loads(body) == {"state": "refused"} and not headers.get("Set-Cookie"))
with open(os.path.join(KEYS, "local.pass")) as f:
    local = f.read().strip()
status, body, _ = call(NEAR, "GET", "/api/slides/now?after=-1", headers={"X-Desk-Local": local})
check("the board's own programs pass with the local pass", status == 200)
status, body, _ = call(WIFI, "GET", "/api/status", headers={"X-Desk-Local": "made-up"})
check("a made-up local pass is refused", status == 403)

# ---- the secret word, a new phone taking over, the reset (step 6)
word = json.dumps({"word": "the blue heron"}).encode()
status, body, _ = call(NEAR, "POST", "/api/trust/word", word, {"Content-Type": "application/json", "Cookie": cookie})
check("an allowed screen can't set the secret word", status == 403)
n, sealed = s.sealed("POST", "/api/trust/word", json.dumps({"word": "short"}).encode())
status, body, _ = s.send("POST", "/api/trust/word", n, sealed)
check("a word too short is refused", status == 400)
n, sealed = s.sealed("POST", "/api/trust/word", word)
status, body, headers = s.send("POST", "/api/trust/word", n, sealed)
check("the owner's phone sets the secret word, sealed", s.opened("POST", "/api/trust/word", status, body, headers) == {"done": True})
check("/api/hello says the desk has a secret word", json.loads(call(NEAR, "GET", "/api/hello")[1])["word"] is True)
new = Phone()
status, got = post_json(WIFI, "/api/trust/claim", {"key": trust.b64(new.public), "name": "new phone", "word": "the blue heron"})
check("taking the desk over over the WiFi is refused, even with the word", status == 403 and "cable" in got["error"])
status, got = post_json(NEAR, "/api/trust/claim", {"key": trust.b64(new.public), "name": "new phone", "word": "the red heron"})
check("a wrong word over the cable is refused", status == 403 and got["error"] == "wrong word")
status, got = post_json(NEAR, "/api/trust/claim", {"key": trust.b64(new.public), "name": "new phone", "word": "the blue heron"})
new.id, new.board = got.get("id"), trust.unb64(got.get("board", ""))
check("the right word over the cable: the new phone owns the desk", status == 200 and bool(new.id))
n, sealed = s.sealed("GET", "/api/status", b"")
status, body, _ = s.send("GET", "/api/status", n, sealed)
check("the old phone's session ends (it would open a new one)", status == 401)
status, got = post_json(WIFI, "/api/trust/session", {"id": me.id, "key": trust.b64(trust.raw(ec.generate_private_key(trust.CURVE).public_key()))})
check("the old phone can't open a new one", status == 403)
status, body, _ = call(NEAR, "GET", "/api/status", headers={"Cookie": cookie})
check("the screens let in under the old phone are locked again", status == 403)
t = new.session(WIFI)
n, sealed = t.sealed("GET", "/api/status", b"")
status, body, headers = t.send("GET", "/api/status", n, sealed)
check("the new phone reads the desk over the WiFi", "error" not in t.opened("GET", "/api/status", status, body, headers))
import subprocess  # noqa: E402
said = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trust.py"), "unclaim", KEYS],
                      input="no\n", capture_output=True, text=True)
check("the reset asks first, and does nothing without yes", "Nothing changed" in said.stderr and json.loads(call(NEAR, "GET", "/api/hello")[1])["claimed"])
said = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trust.py"), "unclaim", KEYS],
                      input="yes\n", capture_output=True, text=True)
hello = json.loads(call(NEAR, "GET", "/api/hello")[1])
check("the reset from a terminal frees the running desk: no owner, no word", said.returncode == 0 and hello["claimed"] is False and hello["word"] is False)
n, sealed = t.sealed("GET", "/api/status", b"")
check("after the reset, the last owner's session ends", t.send("GET", "/api/status", n, sealed)[0] == 401)

print("\n%d of %d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
