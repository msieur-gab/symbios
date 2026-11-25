"""tags: a sound's tags (artist, album artist, album, title, track, length), read from the file itself.

ffprobe took about a second for each sound on the Lyra (23 Nov: 7 s to file and index a 3-track album), almost
all of it starting the program. This reads the few bytes that hold the tags, in Python: MP3 (ID3v2 and the
first frame for the length), M4A/MP4 (the ilst atom, mvhd for the length), FLAC (Vorbis comments, STREAMINFO).
Anything else answers None, and the caller asks ffprobe (OGG, Opus, WAV, WebM: rare in a music folder).

    read(path) → {"artist", "album_artist", "album", "title", "track", "duration"} (missing ones None), or None
    picture(path) → (bytes, type) of the cover inside the sound (MP3 APIC, M4A covr, FLAC PICTURE), or None
    has_picture(path) → whether there is one, without reading it

Standard library only; never reads more than a few hundred kilobytes of a file.
"""
import os
import struct

BITRATES = {  # MPEG-1 layer III, MPEG-2/2.5 layer III, kbit/s by index
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}  # by MPEG version bits


def read(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            if ext == ".mp3":
                return mp3(f, os.path.getsize(path))
            if ext in (".m4a", ".mp4", ".m4b", ".aac") and f.read(8)[4:8] == b"ftyp":
                f.seek(0)
                return mp4(f, os.path.getsize(path))
            if ext == ".flac":
                return flac(f)
    except (OSError, struct.error, ValueError, IndexError, UnicodeDecodeError):
        return None
    return None


def blank():
    return {"artist": None, "album_artist": None, "album": None, "title": None, "track": None, "duration": None}


def number(text):
    """"3/12" or "03" → 3; anything else → None."""
    try:
        return int(str(text).strip().split("/")[0])
    except (TypeError, ValueError):
        return None


def clean(text):
    text = (text or "").replace("\x00", " ").strip()
    return text or None


# ---- MP3: ID3v2 at the start, then the first audio frame for the length ----
def text_frame(data):
    """An ID3 text frame's value: its first byte says the encoding."""
    enc, body = data[0], data[1:]
    if enc == 0:
        return body.decode("latin-1")
    if enc == 1:
        return body.decode("utf-16")
    if enc == 2:
        return body.decode("utf-16-be")
    return body.decode("utf-8", "replace")


def syncsafe(b):
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def mp3(f, size):
    out = blank()
    head = f.read(10)
    audio_at = 0
    if head[:3] == b"ID3":
        version, flags, length = head[3], head[5], syncsafe(head[6:10])
        audio_at = 10 + length + (10 if flags & 0x10 else 0)
        tag = f.read(min(length, 512 * 1024))
        if flags & 0x80 and version < 4:  # the whole tag "unsynchronised": FF 00 stands for FF
            tag = tag.replace(b"\xff\x00", b"\xff")
        pos = 0
        if flags & 0x40 and version >= 3:  # an extended header to step over
            pos = (syncsafe(tag[:4]) if version == 4 else struct.unpack(">I", tag[:4])[0] + 4)
        names = {"TPE1": "artist", "TPE2": "album_artist", "TALB": "album", "TIT2": "title", "TRCK": "track",
                 "TP1": "artist", "TP2": "album_artist", "TAL": "album", "TT2": "title", "TRK": "track"}
        idlen, sizelen = (3, 3) if version == 2 else (4, 4)
        while pos + idlen + sizelen < len(tag):
            fid = tag[pos:pos + idlen]
            if not fid.strip(b"\x00") or not fid.isalnum():
                break
            if version == 2:
                flen = int.from_bytes(tag[pos + 3:pos + 6], "big")
                body_at = pos + 6
            else:
                raw = tag[pos + 4:pos + 8]
                flen = syncsafe(raw) if version == 4 else struct.unpack(">I", raw)[0]
                body_at = pos + 10
            body = tag[body_at:body_at + flen]
            key = names.get(fid.decode("latin-1"))
            if key and body:
                try:
                    out[key] = clean(text_frame(body))
                except UnicodeDecodeError:
                    pass
            pos = body_at + flen
    out["track"] = number(out["track"])
    out["duration"] = mp3_length(f, audio_at, size)
    return out


def mp3_length(f, at, size):
    """The length from the first frame: its Xing/Info or VBRI frame count when there is one, else the bit rate."""
    f.seek(at)
    buf = f.read(64 * 1024)
    i = 0
    while i < len(buf) - 4:
        if buf[i] == 0xFF and buf[i + 1] & 0xE0 == 0xE0:
            b1, b2, b3 = buf[i + 1], buf[i + 2], buf[i + 3]
            ver, layer, rate_i, br_i = (b1 >> 3) & 3, (b1 >> 1) & 3, (b2 >> 2) & 3, b2 >> 4
            if ver != 1 and layer == 1 and rate_i != 3 and br_i not in (0, 15):  # layer III, a real frame
                rate = RATES[ver][rate_i]
                samples = 1152 if ver == 3 else 576
                mono = (b3 >> 6) == 3
                side = (17 if mono else 32) if ver == 3 else (9 if mono else 17)
                frame = buf[i:i + 200]
                for mark, off in ((b"Xing", 4 + side), (b"Info", 4 + side), (b"VBRI", 36)):
                    if frame[off:off + 4] == mark:
                        if mark == b"VBRI":
                            frames = struct.unpack(">I", frame[off + 14:off + 18])[0]
                        elif struct.unpack(">I", frame[off + 4:off + 8])[0] & 1:
                            frames = struct.unpack(">I", frame[off + 8:off + 12])[0]
                        else:
                            break
                        return round(frames * samples / rate, 1)
                kbps = BITRATES[1 if ver == 3 else 2][br_i]
                return round((size - at - i) * 8 / (kbps * 1000), 1)
            i += 1
        else:
            i += 1
    return None


# ---- M4A/MP4: atoms ----
def atoms(f, start, end):
    """The atoms between two offsets: (type, data start, data end)."""
    pos = start
    while pos + 8 <= end:
        f.seek(pos)
        size, kind = struct.unpack(">I4s", f.read(8))
        head = 8
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
            head = 16
        elif size == 0:
            size = end - pos
        if size < head:
            return
        yield kind, pos + head, pos + size
        pos += size


def mp4(f, size):
    out = blank()
    names = {b"\xa9ART": "artist", b"aART": "album_artist", b"\xa9alb": "album", b"\xa9nam": "title"}
    for kind, a, b in atoms(f, 0, size):
        if kind != b"moov":
            continue
        for k2, a2, b2 in atoms(f, a, b):
            if k2 == b"mvhd":
                f.seek(a2)
                v = f.read(1)[0]
                f.seek(a2 + (20 if v == 1 else 12))
                scale, dur = struct.unpack(">IQ" if v == 1 else ">II", f.read(12 if v == 1 else 8))
                if scale:
                    out["duration"] = round(dur / scale, 1)
            if k2 != b"udta":
                continue
            for k3, a3, b3 in atoms(f, a2, b2):
                if k3 != b"meta":
                    continue
                for k4, a4, b4 in atoms(f, a3 + 4, b3):  # meta has 4 bytes of version and flags
                    if k4 != b"ilst":
                        continue
                    for k5, a5, b5 in atoms(f, a4, b4):
                        for k6, a6, b6 in atoms(f, a5, b5):
                            if k6 != b"data":
                                continue
                            f.seek(a6 + 8)  # type and locale
                            value = f.read(min(b6 - a6 - 8, 4096))
                            if k5 in names:
                                out[names[k5]] = clean(value.decode("utf-8", "replace"))
                            elif k5 == b"trkn" and len(value) >= 4:
                                out["track"] = struct.unpack(">H", value[2:4])[0] or None
        break
    return out


# ---- FLAC: metadata blocks ----
def flac(f):
    if f.read(4) != b"fLaC":
        return None
    out = blank()
    names = {"ARTIST": "artist", "ALBUMARTIST": "album_artist", "ALBUM ARTIST": "album_artist", "ALBUM": "album",
             "TITLE": "title", "TRACKNUMBER": "track"}
    while True:
        head = f.read(4)
        if len(head) < 4:
            break
        last, kind, length = head[0] & 0x80, head[0] & 0x7F, int.from_bytes(head[1:4], "big")
        data = f.read(length) if kind in (0, 4) else (f.seek(length, 1) and b"")
        if kind == 0 and len(data) >= 18:  # STREAMINFO: sample rate (20 bits), total samples (36 bits)
            bits = int.from_bytes(data[10:18], "big")
            rate, total = bits >> 44, bits & ((1 << 36) - 1)
            if rate:
                out["duration"] = round(total / rate, 1)
        elif kind == 4:  # VORBIS_COMMENT, little-endian lengths
            vlen = struct.unpack("<I", data[:4])[0]
            pos = 4 + vlen
            count = struct.unpack("<I", data[pos:pos + 4])[0]
            pos += 4
            for _ in range(count):
                n = struct.unpack("<I", data[pos:pos + 4])[0]
                key, _, value = data[pos + 4:pos + 4 + n].decode("utf-8", "replace").partition("=")
                pos += 4 + n
                if key.upper() in names and not out[names[key.upper()]]:
                    out[names[key.upper()]] = clean(value)
        if last:
            break
    out["track"] = number(out["track"])
    return out


# ---- the cover inside the sound (Gab, 24 Nov: tracks loose in ~/Music showed no cover, "it seems like the ID3 tags are
# not right": their tags were right, each with its cover inside; the desk only looked for a cover.jpg beside them) ----
PICTURE_MOST = 8 * 1024 * 1024
INSIDE = "#cover"  # a sound's path with this after it names the cover inside it: /api/raw and /api/fs/raw answer it


def inside_cover(rel, full):
    """rel + INSIDE when the sound at full has a cover inside it, else None."""
    return rel + INSIDE if has_picture(full) else None


def kind_of_image(data, said=""):
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None  # not a picture a browser shows: none at all, never served under another type


def picture(path, peek=False):
    """(bytes, type) of the cover inside the sound, the front cover first; peek: (b"", type) without reading it."""
    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "rb") as f:
            size = os.path.getsize(path)
            if ext == ".mp3":
                return id3_picture(f, peek)
            if ext in (".m4a", ".mp4", ".m4b", ".aac") and f.read(8)[4:8] == b"ftyp":
                return mp4_picture(f, size, peek)
            if ext == ".flac":
                return flac_picture(f, peek)
    except (OSError, struct.error, ValueError, IndexError):
        return None
    return None


def has_picture(path):
    return picture(path, peek=True) is not None


def id3_picture(f, peek):
    head = f.read(10)
    if head[:3] != b"ID3":
        return None
    version, flags, length = head[3], head[5], syncsafe(head[6:10])
    tag = f.read(min(length, PICTURE_MOST + 1024 * 1024))
    if flags & 0x80 and version < 4:
        tag = tag.replace(b"\xff\x00", b"\xff")
    pos = 0
    if flags & 0x40 and version >= 3:
        pos = (syncsafe(tag[:4]) if version == 4 else struct.unpack(">I", tag[:4])[0] + 4)
    idlen = 3 if version == 2 else 4
    found = None
    while pos + idlen + 3 < len(tag):
        fid = tag[pos:pos + idlen]
        if not fid.strip(b"\x00") or not fid.isalnum():
            break
        if version == 2:
            flen, body_at = int.from_bytes(tag[pos + 3:pos + 6], "big"), pos + 6
        else:
            raw = tag[pos + 4:pos + 8]
            flen, body_at = (syncsafe(raw) if version == 4 else struct.unpack(">I", raw)[0]), pos + 10
        body = tag[body_at:body_at + flen]
        if fid in (b"APIC", b"PIC") and len(body) > 4:
            enc = body[0]
            if fid == b"PIC":  # ID3v2.2: a 3-letter format instead of a MIME type
                ptype, rest = body[4], body[5:]
            else:
                end = body.index(b"\x00", 1)
                ptype, rest = body[end + 1], body[end + 2:]
            # the description, ended by one zero byte, or two (aligned) in UTF-16
            if enc in (1, 2):
                i = 0
                while i + 1 < len(rest) and rest[i:i + 2] != b"\x00\x00":
                    i += 2
                data = rest[i + 2:]
            else:
                data = rest[rest.index(b"\x00") + 1:]
            kind = kind_of_image(data)
            if kind and len(data) <= PICTURE_MOST and (found is None or ptype == 3):
                found = (b"" if peek else bytes(data), kind)
                if ptype == 3:
                    break
        pos = body_at + flen
    return found


def mp4_picture(f, size, peek):
    def find(start, end, kind, skip=0):
        for k, a, b in atoms(f, start, end):
            if k == kind:
                return a + skip, b
        return None
    span = (0, size)
    for kind, skip in ((b"moov", 0), (b"udta", 0), (b"meta", 4), (b"ilst", 0), (b"covr", 0), (b"data", 0)):
        span = find(span[0], span[1], kind, skip)
        if not span:
            return None
    a, b = span
    if b - a - 8 > PICTURE_MOST:
        return None
    f.seek(a + 8)  # type and locale
    data = f.read(16 if peek else b - a - 8)
    kind = kind_of_image(data)
    return (b"" if peek else data, kind) if kind else None


def flac_picture(f, peek):
    if f.read(4) != b"fLaC":
        return None
    found = None
    while True:
        head = f.read(4)
        if len(head) < 4:
            break
        last, kind, length = head[0] & 0x80, head[0] & 0x7F, int.from_bytes(head[1:4], "big")
        if kind == 6 and length <= PICTURE_MOST + 4096:  # PICTURE
            block = f.read(length)
            ptype = struct.unpack(">I", block[:4])[0]
            mlen = struct.unpack(">I", block[4:8])[0]
            pos = 8 + mlen
            dlen = struct.unpack(">I", block[pos:pos + 4])[0]
            pos += 4 + dlen + 16
            n = struct.unpack(">I", block[pos:pos + 4])[0]
            data = block[pos + 4:pos + 4 + n]
            image = kind_of_image(data)
            if image and (found is None or ptype == 3):
                found = (b"" if peek else data, image)
                if ptype == 3:
                    break
        else:
            f.seek(length, 1)
        if last:
            break
    return found
