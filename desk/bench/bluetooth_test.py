"""The secure link over Bluetooth (board/desk-bluetooth; SECURE-LINK.md, step 4), without a radio: its values are
called as BlueZ calls them, with a phone played beside them as the companion's trust.js does it. Needs dbus-next
(python3-dbus-next): run it on the board, with throwaway keys.

    python3 bench/bluetooth_test.py
"""
import asyncio
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import trust  # noqa: E402
from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: E402
from cryptography.hazmat.primitives.kdf.hkdf import HKDF  # noqa: E402

loader = importlib.machinery.SourceFileLoader("desk_bluetooth", os.path.join(HERE, "board", "desk-bluetooth"))
bt = importlib.util.module_from_spec(importlib.util.spec_from_loader("desk_bluetooth", loader))
loader.exec_module(bt)

results = []


def read(value):
    """What BlueZ gets from ReadValue: dbus-next's wrapper drops what the method returns, so the method itself."""
    return type(value).ReadValue.__wrapped__(value, {})


def check(name, ok):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name)


class Mouse:
    """Stands in for the uinput mouse: what it was told."""
    def __init__(self):
        self.moves = []

    def move(self, dx, dy):
        self.moves.append((dx, dy))

    def scroll(self, n):
        pass

    def press(self, button, down):
        pass


class Phone:
    def __init__(self):
        self.key = ec.generate_private_key(trust.CURVE)
        self.public = trust.b64(trust.raw(self.key.public_key()))

    def session(self, value):
        """Opens a session through the session value, as the companion does over Bluetooth."""
        once = ec.generate_private_key(trust.CURVE)
        value.WriteValue(json.dumps({"id": self.id, "key": trust.b64(trust.raw(once.public_key()))}).encode(), {})
        got = json.loads(read(value))
        if "error" in got:
            return None
        theirs = trust.unb64(got["key"])
        both = self.key.exchange(ec.ECDH(), trust.point(self.board)) + once.exchange(ec.ECDH(), trust.point(theirs))
        keys = HKDF(hashes.SHA256(), 64, trust.raw(once.public_key()) + theirs, trust.INFO).derive(both)
        return {"sid": got["session"], "up": AESGCM(keys[:32]), "n": 0}

    @staticmethod
    def seal(s, route, text):
        s["n"] += 1
        return s["n"], s["up"].encrypt(trust.nonce(s["n"]), text, trust.bound(s["sid"], route, "up"))

    def frame(self, s, text):
        n, sealed = self.seal(s, "BT steer", text)
        return trust.unb64(s["sid"]) + n.to_bytes(8, "big") + sealed

    def join(self, s, ssid, password):
        n, sealed = self.seal(s, "BT join", json.dumps({"ssid": ssid, "password": password}).encode())
        return json.dumps({"s": s["sid"], "n": n, "c": trust.b64(sealed)}).encode()


async def main():
    steer, join, session = bt.Steer(), bt.Join(), bt.Session()
    steer.mouse = Mouse()
    asked = []

    async def joined(ssid, password):  # stands in for desk-wifi
        asked.append((ssid, password))
        join.state = {"state": "done", "ssid": ssid}
    join.join = joined

    steer.WriteValue(b"m 3 4", {})
    check("with no owner yet, a plain move still steers (as before)", steer.mouse.moves == [(3, 4)])

    me, stranger = Phone(), Phone()
    got = trust.claim(me.public, "bluetooth test")
    me.id, me.board = got["id"], trust.unb64(got["board"])
    stranger.id, stranger.board = me.id, me.board  # knows the owner's id, not the owner's key
    steer.mouse.moves.clear()

    steer.WriteValue(b"m 5 5", {})
    check("once claimed, a plain move is ignored", steer.mouse.moves == [])
    s = me.session(session)
    check("the owner opens a session over Bluetooth", s is not None)
    frame = me.frame(s, b"m 7 -2\nm 1 1")
    steer.WriteValue(frame, {})
    check("the owner's sealed moves steer", steer.mouse.moves == [(7, -2), (1, 1)])
    steer.WriteValue(frame, {})
    check("the same sealed moves again are ignored", steer.mouse.moves == [(7, -2), (1, 1)])
    bent = bytearray(me.frame(s, b"m 9 9"))
    bent[-1] ^= 1
    steer.WriteValue(bytes(bent), {})
    check("a changed frame is ignored", steer.mouse.moves == [(7, -2), (1, 1)])
    t = stranger.session(session)
    steer.WriteValue(stranger.frame(t, b"m 50 50"), {}) if t else None
    check("a stranger using the owner's id can't steer", steer.mouse.moves == [(7, -2), (1, 1)])
    n, sealed = me.seal(s, "BT join", b"m 8 8")  # sealed for the WiFi, sent to the trackpad
    steer.WriteValue(trust.unb64(s["sid"]) + n.to_bytes(8, "big") + sealed, {})
    check("a message sealed for another value doesn't pass", steer.mouse.moves == [(7, -2), (1, 1)])

    join.WriteValue(json.dumps({"ssid": "cafe", "password": "open sesame"}).encode(), {})
    await asyncio.sleep(0.05)
    check("once claimed, a plain WiFi is refused, and the phone is told", asked == [] and "refused" in join.state.get("error", ""))
    join.state = {"state": "idle"}
    whole = me.join(s, "home", "secret")
    join.WriteValue(whole[:40], {"offset": Variant(0)})
    join.WriteValue(whole[40:], {"offset": Variant(40)})
    await asyncio.sleep(0.05)
    check("the owner's sealed WiFi, in two pieces, reaches desk-wifi", asked == [("home", "secret")])

    session.WriteValue(json.dumps({"id": "0" * 16, "key": me.public}).encode(), {})
    check("a session for an unknown phone is refused", json.loads(read(session)) == {"error": "refused"})


class Variant:  # what BlueZ hands as an option: something with a value
    def __init__(self, value):
        self.value = value


folder = tempfile.mkdtemp(prefix="bt-test-")
try:
    trust.start(os.path.join(folder, "keys"))
    asyncio.run(main())
finally:
    shutil.rmtree(folder)
print("\n%d of %d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
