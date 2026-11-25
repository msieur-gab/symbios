"""The Terminal's real shell: a bash on a pty, over a WebSocket, only for requests that are near."""
import base64
import fcntl
import hashlib
import ipaddress
import json
import os
import pty
import re
import select
import struct
import subprocess
import termios

import config


def near(handler):
    """Whether this request may have the real shell: it comes from a network --shell names, and
    the page that sent it is the desk itself, at an address or a .local name (so another site
    open in the same browser can't reach the shell, whatever name it gives the board)."""
    try:
        who = ipaddress.ip_address(handler.client_address[0])
    except ValueError:
        return False
    host = handler.headers.get("Host", "")
    name = host.rsplit(":", 1)[0]
    known = name == "localhost" or name.endswith(".local") or re.fullmatch(r"[\d.]+", name)
    return any(who in net for net in config.SHELL) and bool(known) and handler.headers.get("Origin") in (None, "http://" + host)


def frame(data, op=2):
    """Bytes as one WebSocket frame (binary unless said otherwise)."""
    n = len(data)
    head = bytes([n]) if n < 126 else b"\x7e" + n.to_bytes(2, "big") if n < 65536 else b"\x7f" + n.to_bytes(8, "big")
    return bytes([0x80 | op]) + head + data


def unframe(buf):
    """The first WebSocket frame in buf → (last piece?, kind, bytes, the rest of buf), or None
    while the frame isn't all there. What a browser sends is always masked."""
    if len(buf) < 2:
        return None
    n, i = buf[1] & 127, 2
    if n >= 126:
        i = 4 if n == 126 else 10
        if len(buf) < i:
            return None
        n = int.from_bytes(buf[2:i], "big")
    if not buf[1] & 128 or n > 1_000_000:
        raise ValueError("not a frame a browser sends")
    if len(buf) < i + 4 + n:
        return None
    mask, data = buf[i:i + 4], buf[i + 4:i + 4 + n]
    return bool(buf[0] & 128), buf[0] & 15, bytes(b ^ mask[k & 3] for k, b in enumerate(data)), buf[i + 4 + n:]


class ShellRoutes:
    """The server's /api/shell (mixed into its handler)."""

    def shell(self):
        """A real bash on a pty, over a WebSocket, as symbios does: one shell per Terminal window,
        gone when the window closes. The page sends {"in": keys} and {"rows", "cols"}; the shell's
        bytes go back as they come. Only for requests that are near (see near)."""
        key = self.headers.get("Sec-WebSocket-Key")
        if not near(self):
            return self.fail(403, "the shell opens only on the device itself or over its USB cable")
        if not key or self.headers.get("Upgrade", "").lower() != "websocket":
            return self.fail(400, "expected a WebSocket")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        sock = self.connection
        sock.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode())
        self.close_connection = True
        master, slave = pty.openpty()
        # setsid -c: a session of its own with the pty as its terminal, so Ctrl+C and jobs work
        proc = subprocess.Popen(["setsid", "-c", "bash", "-i"], stdin=slave, stdout=slave, stderr=slave, cwd=config.HOME,
                                env={**os.environ, "HOME": config.HOME, "TERM": "xterm-256color"})
        os.close(slave)
        buf, message = b"", b""
        try:
            while True:
                ready = select.select([master, sock], [], [])[0]
                if master in ready:
                    sock.sendall(frame(os.read(master, 65536)))  # OSError once bash has left
                if sock in ready:
                    piece = sock.recv(65536)
                    if not piece:
                        break
                    buf += piece
                    while (got := unframe(buf)):
                        last, kind, data, buf = got
                        if kind == 8:
                            return
                        if kind == 9:
                            sock.sendall(frame(data, 10))
                        if kind > 2:
                            continue
                        message += data
                        if not last:
                            continue
                        said, message = json.loads(message), b""
                        if "in" in said:
                            os.write(master, said["in"].encode())
                        elif "rows" in said:
                            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", int(said["rows"]), int(said["cols"]), 0, 0))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass  # bash left, the window closed, or what came wasn't ours
        finally:
            os.close(master)  # hangs up the pty: bash and what it started get SIGHUP
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            try:
                sock.sendall(frame(b"", 8))
            except OSError:
                pass
