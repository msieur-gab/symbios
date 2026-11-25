"""The secure link's board side (trust.py), with a phone played next to it: the claim, sessions, and every way a message
must not open. The phone does what the companion's Web Crypto will do, step by step, so this is also the recipe for it.

    python3 bench/trust_test.py    # on the laptop, then on the board: PASS/FAIL per check, then the time it takes
"""
import os
import resource
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import trust  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402
from cryptography.exceptions import InvalidTag  # noqa: E402


class Phone:
    """What the companion will hold: its own key (never leaves the phone), the board's public key once claimed."""

    def __init__(self):
        self.key = ec.generate_private_key(trust.CURVE)
        self.public = trust.b64(trust.raw(self.key.public_key()))
        self.id = trust.key_id(trust.unb64(self.public))
        self.board = None

    def open_session(self):
        once = ec.generate_private_key(trust.CURVE)
        answer = trust.begin(self.id, trust.b64(trust.raw(once.public_key())))
        theirs = trust.point(trust.unb64(answer["key"]))
        both = self.key.exchange(ec.ECDH(), trust.point(trust.unb64(self.board))) + once.exchange(ec.ECDH(), theirs)
        keys = HKDF(hashes.SHA256(), 64, trust.raw(once.public_key()) + trust.unb64(answer["key"]), trust.INFO).derive(both)
        return PhoneSession(answer["session"], keys)


class PhoneSession:
    def __init__(self, sid, keys):
        self.sid, self.up, self.down, self.n = sid, AESGCM(keys[:32]), AESGCM(keys[32:]), 0

    def seal(self, route, text):
        self.n += 1
        return self.n, self.up.encrypt(trust.nonce(self.n), text, trust.bound(self.sid, route, "up"))

    def unseal(self, n, route, sealed):
        return self.down.decrypt(trust.nonce(n), sealed, trust.bound(self.sid, route, "down"))


results = []


def check(name, ok):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name)


def refused(fn):
    try:
        fn()
    except trust.Refused:
        return True
    return False


folder = tempfile.mkdtemp(prefix="trust-test-")
try:
    trust.start(os.path.join(folder, "desk-trust"))
    board = trust.board_key()
    check("the board's key is readable by its user only", os.stat(os.path.join(folder, "desk-trust", "board.pem")).st_mode & 0o777 == 0o600)
    trust.start(os.path.join(folder, "desk-trust"))
    check("the board keeps its key across a restart", trust.board_key() == board)
    check("a board with no owner says so", not trust.claimed())

    me, stranger = Phone(), Phone()
    answer = trust.claim(me.public, "Gab's phone")
    me.board = answer["board"]
    check("the claim gives the board's key back", answer["board"] == board and answer["id"] == me.id)
    check("a second claim is refused", refused(lambda: trust.claim(stranger.public)))
    trust.start(os.path.join(folder, "desk-trust"))
    check("the owner is still there after a restart", trust.claimed() and me.id in trust.OWNERS)
    stranger.board = board
    check("a phone that isn't an owner can't open a session", refused(stranger.open_session))

    s = me.open_session()
    n, sealed = s.seal("POST /api/inbox", b"a shared link")
    check("a message from the owner opens", trust.unseal(s.sid, n, "POST /api/inbox", sealed) == b"a shared link")
    check("the same message again is refused", refused(lambda: trust.unseal(s.sid, n, "POST /api/inbox", sealed)))
    m, answer = trust.seal(s.sid, "POST /api/inbox", b'{"kept": true}')
    check("the board's answer opens on the phone", s.unseal(m, "POST /api/inbox", answer) == b'{"kept": true}')

    n2, a = s.seal("POST /api/say", b"first")
    n3, b = s.seal("POST /api/say", b"second")
    check("messages arriving out of order both open", trust.unseal(s.sid, n3, "POST /api/say", b) == b"second"
          and trust.unseal(s.sid, n2, "POST /api/say", a) == b"first")
    n4, c = s.seal("POST /api/say", b"list my files")
    check("a message moved to another route doesn't open", refused(lambda: trust.unseal(s.sid, n4, "POST /api/exec", c)))
    bent = bytearray(c)
    bent[0] ^= 1
    check("a changed message doesn't open", refused(lambda: trust.unseal(s.sid, n4, "POST /api/say", bytes(bent))))
    check("a changed number doesn't open", refused(lambda: trust.unseal(s.sid, n4 + 1, "POST /api/say", c)))
    other = me.open_session()
    check("a message from one session doesn't open in another", refused(lambda: trust.unseal(other.sid, n4, "POST /api/say", c)))
    check("the board's answer can't pass for the phone's", refused(lambda: trust.unseal(s.sid, m, "POST /api/inbox", answer)))
    try:
        s.unseal(m, "POST /api/inbox", c)
        check("the phone's message can't pass for the board's answer", False)
    except InvalidTag:
        check("the phone's message can't pass for the board's answer", True)
    for _ in range(trust.WINDOW + 1):
        s.seal("GET /api/status", b"")
    nl, last = s.seal("GET /api/status", b"")
    trust.unseal(s.sid, nl, "GET /api/status", last)
    check("a number older than the window is refused", refused(lambda: trust.unseal(s.sid, n4, "POST /api/say", c)))

    # someone who saw the claim and every message, and holds the owner's id, but not the owner's key
    thief = Phone()
    thief.id, thief.board = me.id, board
    try:
        t = thief.open_session()
        n5, d = t.seal("POST /api/exec", b"rm -rf ~")
        check("a stranger using the owner's id can't make a message that opens", refused(lambda: trust.unseal(t.sid, n5, "POST /api/exec", d)))
    except trust.Refused:
        check("a stranger using the owner's id can't make a message that opens", True)
    check("a made-up session is refused", refused(lambda: trust.unseal("nothing", 1, "GET /api/status", b"x" * 32)))
    check("a key that isn't a point on the curve is refused", refused(lambda: trust.begin(me.id, trust.b64(b"\x04" + bytes(64)))))

    # the secret word (step 6): a new phone takes the desk over; the reset frees it
    check("a word too short is refused", refused(lambda: trust.set_word("short")))
    check("before a word is set, taking the desk over is refused", refused(lambda: trust.claim(Phone().public, "new", "anything at all")))
    t0 = time.perf_counter()
    trust.set_word("the blue heron")
    print("      setting the word took %.0f ms" % ((time.perf_counter() - t0) * 1000))
    check("the board keeps no word, only its fingerprint", b"heron" not in open(os.path.join(trust.FOLDER, "word.json"), "rb").read())
    old = me.open_session()
    n6, e = old.seal("GET /api/status", b"")
    new = Phone()
    check("a new phone without the word can't claim", refused(lambda: trust.claim(new.public, "new")))
    check("a wrong word is refused", refused(lambda: trust.claim(new.public, "new", "the red heron")))
    got = trust.claim(new.public, "new", "the blue heron")
    new.board = got["board"]
    check("the right word: the new phone owns the desk, alone", list(trust.OWNERS) == [new.id] and trust.claimed())
    check("the old phone's session ends", refused(lambda: trust.unseal(old.sid, n6, "GET /api/status", e)))
    check("the old phone can't open a new one", refused(lambda: me.open_session()))
    s = new.open_session()
    n7, f = s.seal("GET /api/status", b"")
    check("the new phone talks to the desk", trust.unseal(s.sid, n7, "GET /api/status", f) == b"")
    for _ in range(3):  # the right word just cleared the count
        refused(lambda: trust.claim(Phone().public, "x", "nope nope nope"))
    check("after 3 wrong words in a row, the next waits a minute", 55 <= trust.wait_left() <= 60)
    check("even the right word waits", refused(lambda: trust.claim(me.public, "back", "the blue heron")))
    trust.write("tries.json", b'{"wrong": 3, "until": 0}')
    refused(lambda: trust.claim(Phone().public, "x", "nope nope nope"))
    check("each wrong word after that doubles the wait", 115 <= trust.wait_left() <= 120)
    trust.write("tries.json", b'{"wrong": 30, "until": 0}')
    refused(lambda: trust.claim(Phone().public, "x", "nope nope nope"))
    check("the wait stops at an hour", 3590 <= trust.wait_left() <= 3600)
    trust.write("tries.json", b"{}")
    trust.claim(new.public, "new", "the blue heron")
    check("the right word clears the count", trust.wait_left() == 0 and open(os.path.join(trust.FOLDER, "tries.json")).read() == "{}")
    era = trust.era()
    trust.unclaim()
    check("the reset: no owner, no word, a new era", not trust.claimed() and not trust.has_word() and trust.era() != era)
    check("the reset ends the sessions", refused(lambda: trust.unseal(s.sid, n7 + 1, "GET /api/status", f)))
    got = trust.claim(me.public, "me again")
    check("after the reset, the next phone claims as the first time", list(trust.OWNERS) == [me.id])

    print()
    t0 = time.perf_counter()
    for _ in range(20):
        me.open_session()
    print("opening a session (board side and phone side together): %.1f ms" % ((time.perf_counter() - t0) / 20 * 1000))
    s = me.open_session()
    for size, label in ((1000, "1 KB (a shared link, a sentence to TermNL)"), (1_000_000, "1 MB (a voice memo)")):
        text = os.urandom(size)
        t0 = time.perf_counter()
        for _ in range(10):
            n, sealed = s.seal("POST /api/inbox", text)
            trust.unseal(s.sid, n, "POST /api/inbox", sealed)
        print("sealing and opening %s: %.2f ms" % (label, (time.perf_counter() - t0) / 10 * 1000))
    print("memory of this test, at most: %d MB" % (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024))
finally:
    shutil.rmtree(folder)

print("\n%d of %d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
