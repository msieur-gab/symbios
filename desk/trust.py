"""trust: the board's side of the secure link with its owner's phone (SECURE-LINK.md). Keys, the claim, sessions,
and sealing and opening messages. Nothing here knows about routes or transports: server.py (the gate, step 3) and
desk-bluetooth (step 4) carry the bytes; this file decides whether they open.

    /var/lib/desk-trust/board.pem      the board's key, made on first start, never in the SD image
    /var/lib/desk-trust/owners.json    the phones that claimed it: their public keys
    /var/lib/desk-trust/word.json      the owner's secret word, as a slow fingerprint (scrypt), never the word itself
    /var/lib/desk-trust/tries.json     the wrong words in a row, and until when the next one waits

Outside the home folder (board/install.sh makes it, readable by the desk's user only), so packing the home folder never
packs a key. A file is written as a new one renamed over the old, as in embed.py.

The claim: the phone sends its public key, the board keeps it and answers with its own (only while it has no owner;
that it comes over the cable is the server's check). A session: the phone sends a key made for this session only, the
board makes one too, and both work out the session's keys from the two pairs: the owner's and the board's (only these
two can) and the two one-time ones (a recorded session stays closed even if a key is later stolen). Then every message,
both ways, is sealed: encrypted, signed, bound to its route, with a number that only opens once.

Standard pieces, the same in the browser's Web Crypto: ECDH on P-256, keys as raw 65-byte points; HKDF-SHA256;
AES-GCM with a 16-byte tag after the text, its 12-byte nonce the message's number (4 zero bytes, 8 bytes big-endian).

The secret word (SECURE-LINK.md, step 6): set by the owner's phone, sealed, at the claim or later. Over the cable only,
a new phone that gives it takes the desk over: it becomes the owner, the old phone's sessions end. After 3 wrong words in
a row, the next waits 1 minute, then 2, 4… up to an hour, kept in a file so a restart doesn't skip it. With no phone
and no word, the reset frees the desk, files kept (Gab, 2026-10-27: "ssh recovery through terminal"):

    python3 trust.py unclaim [folder]    # on the board, over SSH or on its own screen: the desk has no owner again

    python3 bench/trust_test.py    # the phone and the board played together: claim, sessions, what must not open
"""
import base64
import hashlib
import json
import os
import secrets
import threading
import time

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.exceptions import InvalidTag

CURVE = ec.SECP256R1()
INFO = b"symbiot session v1"  # changes when the recipe does: an old phone and a new board never half-agree
IDLE = 3600  # seconds: a session no one used for this long is forgotten
SESSIONS = 32  # at most, all owners together; the oldest goes first (a stranger can open sessions, never use them)
WINDOW = 256  # messages may arrive out of order (the phone sends several at once): the last 256 numbers are remembered
WORD = {"n": 2 ** 15, "r": 8, "p": 1}  # scrypt's cost for the secret word: 32 MB and a fraction of a second on the board
SHORTEST = 8  # characters in a secret word, at least
FREE_TRIES = 3  # wrong words in a row before the waits begin
LONGEST_WAIT = 3600

FOLDER = None
BOARD = None  # the board's private key
OWNERS = {}  # phone id → {"key": base64 raw point, "name", "added"}
READ = None  # when owners.json was read: the desk's server and desk-bluetooth each load it, either may see a claim first
LIVE = {}  # session id → Session
LOCK = threading.Lock()


class Refused(Exception):
    """A claim, a session or a message that doesn't open. The reason is for the log, never for the asker."""


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def raw(public):
    return public.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def point(data):
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(CURVE, data)
    except ValueError:
        raise Refused("not a key")


def key_id(key):
    """A key's short name: the start of its hash, the same on both sides (a phone's id; the board's, in /api/hello)."""
    return hashlib.sha256(key).hexdigest()[:16]


def write(name, data, mode=0o600):
    """On the SD card before the desk answers: the board runs on the phone's power through the cable, so unplugging is
    a power cut, and a file only in memory then is lost (2026-10-27: a takeover, then the cable out, and the board
    woke up with the old owner)."""
    path = os.path.join(FOLDER, name)
    fd = os.open(path + ".new", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(path + ".new", path)
    folder = os.open(FOLDER, os.O_RDONLY)  # the rename too
    try:
        os.fsync(folder)
    finally:
        os.close(folder)


def start(folder):
    """Loads the board's key and its owners, or makes the key the first time."""
    global FOLDER, BOARD, OWNERS
    FOLDER = folder
    os.makedirs(folder, mode=0o700, exist_ok=True)
    pem = os.path.join(folder, "board.pem")
    if not os.path.exists(pem):
        write("board.pem", ec.generate_private_key(CURVE).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    with open(pem, "rb") as f:
        BOARD = serialization.load_pem_private_key(f.read(), None)
    fresh()


def fresh():
    """The owners as owners.json has them now: read again when it changed since (a claim made through the other
    process)."""
    global OWNERS, READ
    try:
        when = os.stat(os.path.join(FOLDER, "owners.json")).st_mtime_ns
    except FileNotFoundError:
        OWNERS, READ = {}, None
        return
    if when != READ:
        with open(os.path.join(FOLDER, "owners.json")) as f:
            OWNERS, READ = json.load(f), when


def local_pass():
    """A pass for the board's own programs (desk-bluetooth) to reach the desk's server: made once, in a file only the
    desk's user reads; sent as X-Desk-Local."""
    path = os.path.join(FOLDER, "local.pass")
    if not os.path.exists(path):  # the server and desk-bluetooth may start together: the first one's pass wins
        mine = "local.%d" % os.getpid()
        write(mine, secrets.token_urlsafe(24).encode())
        try:
            os.link(os.path.join(FOLDER, mine), path)
        except FileExistsError:
            pass
        os.remove(os.path.join(FOLDER, mine))
    with open(path) as f:
        return f.read().strip()


def era():
    """Who owns the desk now, as one string: it changes when the owner does (a takeover, the reset), so whatever was let
    in under the old owner (a screen's pass) ends."""
    fresh()
    return ",".join(sorted(OWNERS))


def board_key():
    return b64(raw(BOARD.public_key()))


def claimed():
    fresh()
    return bool(OWNERS)


def claim(key, name="", word=None):
    """The first phone becomes the owner: its public key kept, the board's given back. Once owned, refused, unless the
    phone gives the secret word: then it takes the desk over, and the old phone's sessions end (a lost or stolen phone)."""
    data = unb64(key)
    point(data)
    if word is not None:
        check_word(word)  # slow on purpose: outside the lock
    with LOCK:
        fresh()
        if OWNERS and word is None:
            raise Refused("already claimed")
        who = key_id(data)
        owners = {who: {"key": key, "name": name[:60], "added": time.strftime("%Y-%m-%d %H:%M")}}
        write("owners.json", json.dumps(owners, indent=1).encode())
        fresh()
        LIVE.clear()
    return {"id": who, "board": board_key()}


def has_word():
    return os.path.exists(os.path.join(FOLDER, "word.json"))


def set_word(word):
    """The owner's phone sets or changes the secret word (sealed: the server only calls this for an owner's session)."""
    if not isinstance(word, str) or len(word) < SHORTEST:
        raise Refused("a secret word has %d characters at least" % SHORTEST)
    salt = secrets.token_bytes(16)
    made = hashlib.scrypt(word.encode(), salt=salt, maxmem=64 * 2 ** 20, dklen=32, **WORD)
    write("word.json", json.dumps({"salt": b64(salt), "hash": b64(made), **WORD}).encode())
    write("tries.json", b"{}")


def wait_left():
    """Seconds before the next word may be tried (0: now)."""
    try:
        with open(os.path.join(FOLDER, "tries.json")) as f:
            return max(0, int(json.load(f).get("until", 0) - time.time()))
    except (FileNotFoundError, ValueError):
        return 0


def check_word(word):
    """Refused unless this is the secret word, and not while a wait runs. Every wrong word counts, in a file."""
    if not has_word():
        raise Refused("this desk has no secret word")
    left = wait_left()
    if left:
        raise Refused("wait %d" % left)
    with open(os.path.join(FOLDER, "word.json")) as f:
        kept = json.load(f)
    made = hashlib.scrypt(str(word).encode(), salt=unb64(kept["salt"]), maxmem=64 * 2 ** 20, dklen=32,
                          n=kept["n"], r=kept["r"], p=kept["p"])
    with LOCK:
        try:
            with open(os.path.join(FOLDER, "tries.json")) as f:
                tries = json.load(f)
        except (FileNotFoundError, ValueError):
            tries = {}
        if secrets.compare_digest(made, unb64(kept["hash"])):
            write("tries.json", b"{}")
            return
        wrong = tries.get("wrong", 0) + 1
        wait = min(LONGEST_WAIT, 60 * 2 ** (wrong - FREE_TRIES)) if wrong >= FREE_TRIES else 0
        write("tries.json", json.dumps({"wrong": wrong, "until": time.time() + wait}).encode())
    raise Refused("wrong word" + (" (wait %d)" % wait if wait else ""))


def unclaim():
    """The reset: no owner, no secret word, no session. The files in the home folder stay as they are."""
    with LOCK:
        for name in ("owners.json", "word.json", "tries.json"):
            try:
                os.remove(os.path.join(FOLDER, name))
            except FileNotFoundError:
                pass
        fresh()
        LIVE.clear()


class Session:
    def __init__(self, who, up, down):
        self.who, self.up, self.down = who, AESGCM(up), AESGCM(down)
        self.sent = 0  # the board's numbers, one per answer
        self.top, self.seen = 0, set()  # the phone's numbers: the highest, and those opened within the window
        self.used = time.time()


def begin(who, key):
    """A phone opens a session with a key made for it: the board answers with its own one-time key and the session's
    id. Nothing in the answer is secret; only the owner can use it."""
    fresh()
    owner = OWNERS.get(who)
    if not owner:
        raise Refused("not an owner")
    theirs = point(unb64(key))
    mine = ec.generate_private_key(CURVE)
    both = BOARD.exchange(ec.ECDH(), point(unb64(owner["key"]))) + mine.exchange(ec.ECDH(), theirs)
    keys = HKDF(hashes.SHA256(), 64, unb64(key) + raw(mine.public_key()), INFO).derive(both)
    sid = b64(secrets.token_bytes(12))
    with LOCK:
        now = time.time()
        for old in [s for s, v in LIVE.items() if now - v.used > IDLE]:
            del LIVE[old]
        while len(LIVE) >= SESSIONS:
            del LIVE[min(LIVE, key=lambda s: LIVE[s].used)]
        LIVE[sid] = Session(who, keys[:32], keys[32:])
    return {"session": sid, "key": b64(raw(mine.public_key()))}


def nonce(n):
    return bytes(4) + n.to_bytes(8, "big")


def bound(sid, route, way):
    """What a message is bound to besides its text: its session, its route, and which way it goes."""
    return ("%s %s %s" % (sid, way, route)).encode()


def unseal(sid, n, route, sealed):
    """A message from the phone: its text, or Refused if it doesn't open or its number was already used."""
    with LOCK:
        s = LIVE.get(sid)
        if s:
            fresh()
            if s.who not in OWNERS:  # the desk changed hands since (a takeover, the reset), maybe through the other process
                del LIVE[sid]
                s = None
        if not s:
            raise Refused("no such session")
        if n < 1 or n >= 2 ** 63 or n <= s.top - WINDOW or n in s.seen:
            raise Refused("number already used")
    try:
        text = s.up.decrypt(nonce(n), sealed, bound(sid, route, "up"))
    except InvalidTag:
        raise Refused("does not open")
    with LOCK:
        if n in s.seen:  # two copies arriving at once: only the first counts
            raise Refused("number already used")
        s.seen.add(n)
        if n > s.top:
            s.top = n
            s.seen = {m for m in s.seen if m > n - WINDOW}
        s.used = time.time()
    return text


def seal(sid, route, text):
    """An answer to the phone: (its number, the sealed bytes)."""
    with LOCK:
        s = LIVE.get(sid)
        if not s:
            raise Refused("no such session")
        s.sent += 1
        n = s.sent
    return n, s.down.encrypt(nonce(n), text, bound(sid, route, "down"))


def owner_of(sid):
    s = LIVE.get(sid)
    return s.who if s else None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or sys.argv[1] != "unclaim":
        sys.exit("python3 trust.py unclaim [folder]    frees the desk: no owner, no secret word (files kept)")
    folder = sys.argv[2] if len(sys.argv) > 2 else "/var/lib/desk-trust"
    if not os.path.exists(os.path.join(folder, "board.pem")):
        sys.exit("no desk keys in %s" % folder)
    start(folder)
    print("This desk is owned by: %s" % (", ".join("%s (%s, since %s)" % (w, o["name"], o["added"]) for w, o in OWNERS.items()) or "nobody"))
    if input("Free it? Its owner's phone is shut out, its secret word forgotten; files stay. Type yes: ").strip() != "yes":
        sys.exit("Nothing changed.")
    unclaim()
    print("Done: the desk has no owner. The next phone to claim it (over the cable, or with the QR code a screen near it shows) becomes its owner.")
