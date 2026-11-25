"""Meshtastic's client API, the part a desk needs: what the radio says (FromRadio), what we ask it (ToRadio).

Field numbers come from meshtastic/protobufs v2.6.7 (mesh.proto, channel.proto, config.proto, portnums.proto,
telemetry.proto). Over a serial line or USB, each message travels in a frame: 0x94 0xC3, its length
on two bytes, then the message; the radio's debug text may sit between frames.
"""
import os

from .wire import decode, encode, first, text, sint32, float32

BROADCAST = 0xFFFFFFFF
TEXT, POSITION, NODEINFO, ROUTING, TEXT_COMPRESSED, TELEMETRY = 1, 3, 4, 5, 7, 67
ROUTING_ERRORS = {0: None, 1: "no route", 2: "refused", 3: "timed out", 4: "no interface", 5: "gave up after retries",
                  6: "no such channel", 7: "too large", 8: "no answer", 32: "not allowed", 33: "not authorized",
                  34: "key unknown", 35: "key needed"}
MOST_TEXT = 200  # bytes of UTF-8 a text message can carry (Meshtastic's own apps stop there)
START1, START2, MOST_FRAME = 0x94, 0xC3, 512

# the radio's setup, as config.proto v2.6.7 names it (checked against the file, 24 Nov)
REGIONS = ["unset", "US", "EU_433", "EU_868", "CN", "JP", "ANZ", "KR", "TW", "RU", "IN", "NZ_865", "TH", "LORA_24", "UA_433",
           "UA_868", "MY_433", "MY_919", "SG_923", "PH_433", "PH_868", "PH_915"]  # RegionCode
PRESETS = {0: "Long Fast", 1: "Long Slow", 3: "Medium Slow", 4: "Medium Fast", 5: "Short Slow", 6: "Short Fast",
           7: "Long Moderate", 8: "Short Turbo"}  # ModemPreset
ROLES = {0: "Client", 1: "Client mute", 2: "Router", 4: "Repeater", 5: "Tracker", 6: "Sensor", 7: "TAK",
         8: "Client hidden", 9: "Lost and found", 10: "TAK tracker", 11: "Router late"}  # DeviceConfig.Role


def node_id(num):
    return "!%08x" % num


def frame(message):
    return bytes([START1, START2, len(message) >> 8, len(message) & 0xFF]) + message


class Deframer:
    """Bytes as they come from the line, messages out. What isn't a frame (the radio's log text) is kept apart."""

    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf += data
        out = []
        while True:
            i = self.buf.find(bytes([START1, START2]))
            if i < 0:
                del self.buf[:max(0, len(self.buf) - 1)]  # keep a last 0x94: the frame may start there
                return out
            del self.buf[:i]
            if len(self.buf) < 4:
                return out
            size = self.buf[2] << 8 | self.buf[3]
            if size > MOST_FRAME:  # not a real header: look further on
                del self.buf[:1]
                continue
            if len(self.buf) < 4 + size:
                return out
            out.append(bytes(self.buf[4:4 + size]))
            del self.buf[:4 + size]


# ---- what we ask the radio ----

def want_config(nonce):
    return encode((3, "v", nonce))


def heartbeat():
    return encode((7, "b", b""))


def disconnect():
    return encode((4, "v", 1))


def new_id():
    return int.from_bytes(os.urandom(4), "little") or 1


def text_packet(words, to=BROADCAST, channel=0, packet_id=None, reply_id=None, emoji=False):
    data = encode((1, "v", TEXT), (2, "b", words.encode()), (7, "f32", reply_id), (8, "f32", 1 if emoji else None))
    packet = encode((2, "f32", to), (3, "v", channel or None), (4, "b", data), (6, "f32", packet_id or new_id()),
                    (10, "v", 1))  # want_ack: the radio says when the message was heard (or that it failed)
    return encode((1, "b", packet))


# ---- what the radio says ----

def from_radio(message):
    """One FromRadio message, as {"kind": …, …}."""
    f = decode(message)
    if 2 in f:
        return {"kind": "packet", **packet(first(f, 2))}
    if 3 in f:
        return {"kind": "me", "num": first(decode(first(f, 3)), 1)}
    if 4 in f:
        return {"kind": "node", **node(first(f, 4))}
    if 10 in f:
        return {"kind": "channel", **channel(first(f, 10))}
    if 5 in f:
        return {"kind": "config", **config(first(f, 5))}
    if 13 in f:
        return {"kind": "metadata", "firmware": text(decode(first(f, 13)), 1)}
    if 7 in f:
        return {"kind": "ready", "nonce": first(f, 7)}
    if 8 in f:
        return {"kind": "rebooted"}
    if 11 in f:
        q = decode(first(f, 11))
        return {"kind": "queue", "free": first(q, 2, 0), "most": first(q, 3, 0), "id": first(q, 4)}
    return {"kind": "other", "fields": sorted(f)}


def packet(raw):
    f = decode(raw)
    p = {"from": first(f, 1, 0), "to": first(f, 2, 0), "channel": first(f, 3, 0), "id": first(f, 6, 0),
         "rx_time": first(f, 7), "snr": float32(first(f, 8)), "rssi": sint32(first(f, 12)),
         "hop_limit": first(f, 9), "hop_start": first(f, 15), "via_mqtt": bool(first(f, 14, 0)),
         "encrypted": 5 in f, "port": None}
    if p["rssi"] == 0:
        p["rssi"] = None
    if 4 in f:
        d = decode(first(f, 4))
        p.update(port=first(d, 1, 0), payload=first(d, 2, b""), request_id=first(d, 6), reply_id=first(d, 7),
                 emoji=bool(first(d, 8, 0)))
    return p


def user(raw):
    u = decode(raw)
    return {"id": text(u, 1), "long": text(u, 2), "short": text(u, 3), "hw": first(u, 5, 0)}


def position(raw):
    f = decode(raw)
    lat, lon = sint32(first(f, 1)), sint32(first(f, 2))
    if not lat and not lon:
        return None
    return {"lat": lat / 1e7, "lon": lon / 1e7, "alt": sint32(first(f, 3))}


def node(raw):
    f = decode(raw)
    n = {"num": first(f, 1, 0), "snr": float32(first(f, 4)), "last_heard": first(f, 5), "hops": first(f, 9),
         "via_mqtt": bool(first(f, 8, 0))}
    if 2 in f:
        n.update(user(first(f, 2)))
    if 3 in f:
        n["position"] = position(first(f, 3))
    if 6 in f:
        n["battery"] = first(decode(first(f, 6)), 1)
    return n


def privacy(psk):
    """What a channel's key makes of it (channel.proto): none, "open" (anyone hears it as it is); one byte, "public" (one of
    Meshtastic's known keys: anyone with the app reads it); its own 16 or 32 bytes, "private" (only those given the key)."""
    if not psk or psk == b"\x00":
        return "open"
    return "public" if len(psk) == 1 else "private"


def channel(raw):
    """A channel's index, role (0 off, 1 primary, 2 secondary), name, and what its key makes of it; the key itself is
    dropped here, never kept nor shown."""
    f = decode(raw)
    s = decode(first(f, 2, b""))
    return {"index": sint32(first(f, 1, 0)), "role": first(f, 3, 0), "name": text(s, 3) or "", "privacy": privacy(first(s, 2, b""))}


def config(raw):
    """One part of the radio's setup (Config): its LoRa part (region, preset, hops) or its device part (role); others
    are passed over."""
    c = decode(raw)
    if 6 in c:
        lo = decode(first(c, 6))
        region = first(lo, 7, 0)
        return {"region": REGIONS[region] if region < len(REGIONS) else "region %d" % region,
                "preset": PRESETS.get(first(lo, 2, 0), "preset %d" % first(lo, 2, 0)) if first(lo, 1, 0) else "custom",
                "hops": first(lo, 8, 0) or None}
    if 1 in c:
        role = first(decode(first(c, 1)), 1, 0)
        return {"role": ROLES.get(role, "role %d" % role)}
    return {}


def routing_error(payload):
    """A ROUTING_APP payload: None when it says the message went through, else why it didn't."""
    code = first(decode(payload), 3, 0)
    return ROUTING_ERRORS.get(code, "error %d" % code)


def battery(payload):
    """A TELEMETRY_APP payload: the battery level in it, if it carries the device's metrics."""
    f = decode(payload)
    return first(decode(first(f, 2)), 1) if 2 in f else None
