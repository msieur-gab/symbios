"""Protocol Buffers on the wire, the little Meshtastic needs: no protobuf library, no generated code.

A message is a run of fields, each a number and a value. decode() gives {number: [values]}, every
value as it came (an int for a varint or a fixed32, bytes for a string or a message inside);
the caller knows what each number means (mesh.py). encode() takes (number, kind, value) triples.
"""
import struct

VARINT, FIXED64, BYTES, FIXED32 = 0, 1, 2, 5


def varint(n):
    n &= (1 << 64) - 1  # a negative int32 goes out as ten bytes, as protobuf sends it
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def read_varint(buf, i):
    n = shift = 0
    while True:
        if i >= len(buf):
            raise ValueError("cut varint")
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << shift
        if not b & 0x80:
            return n, i
        shift += 7
        if shift > 63:
            raise ValueError("varint too long")


def decode(buf):
    fields, i = {}, 0
    while i < len(buf):
        key, i = read_varint(buf, i)
        number, kind = key >> 3, key & 7
        if kind == VARINT:
            value, i = read_varint(buf, i)
        elif kind == FIXED32:
            value, i = struct.unpack_from("<I", buf, i)[0], i + 4
        elif kind == FIXED64:
            value, i = struct.unpack_from("<Q", buf, i)[0], i + 8
        elif kind == BYTES:
            size, i = read_varint(buf, i)
            if i + size > len(buf):
                raise ValueError("cut field")
            value, i = bytes(buf[i:i + size]), i + size
        else:
            raise ValueError("unknown wire type %d" % kind)
        fields.setdefault(number, []).append(value)
    return fields


def encode(*fields):
    """encode((1, "v", 5), (2, "s", "hi"), (3, "f32", 0xFFFFFFFF), (4, "b", b"…")); None values are left out."""
    out = bytearray()
    for number, kind, value in fields:
        if value is None:
            continue
        if kind == "v":
            out += varint(number << 3 | VARINT) + varint(int(value))
        elif kind == "f32":
            out += varint(number << 3 | FIXED32) + struct.pack("<I", int(value) & 0xFFFFFFFF)
        elif kind in ("b", "s"):
            data = value.encode() if isinstance(value, str) else bytes(value)
            out += varint(number << 3 | BYTES) + varint(len(data)) + data
        else:
            raise ValueError("unknown kind " + kind)
    return bytes(out)


# reading one value of a decoded message, by its meaning
def first(fields, number, default=None):
    values = fields.get(number)
    return values[-1] if values else default


def text(fields, number):
    value = first(fields, number)
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else None


def sint32(value):
    """An int32 sent as a varint (ten bytes when negative), or an sfixed32, back to its sign."""
    if value is None:
        return None
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value & 0x80000000 else value


def float32(value):
    return None if value is None else struct.unpack("<f", struct.pack("<I", value))[0]
