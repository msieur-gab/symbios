"""One radio, kept connected: it asks for the radio's nodes and channels, reads what the mesh says, sends
text, keeps every message in the archive, and tells waiting clients what changed.

Everything that changes becomes an event with a number that only grows ({"seq", "type", …}); a
client asks wait(after=its last number) and gets what came since. The numbers start from the clock
at start, so they still grow across a restart.
"""
import collections
import threading
import time

from . import mesh
from .link import open_link

BEAT = 300        # seconds between heartbeats: a radio on serial drops a client that stays silent ~15 min
ANSWER = 15       # seconds the radio has to answer the first question before the line is tried again
RETRY = 5
QUIET = 120      # seconds a port that didn't answer is left alone, the others asked first


class NoAnswer(OSError):
    """The line opened, but nothing on it spoke Meshtastic."""


class Radio:
    def __init__(self, device="auto", archive=None, log=None):
        self.device, self.archive, self.log = device, archive, log or (lambda line: None)
        self.cond = threading.Condition()
        self.write_lock = threading.Lock()
        self.events = collections.deque(maxlen=500)
        self.seq = int(time.time() * 1000)
        self.link = None
        self.connected = False
        self.problem = "starting"
        self.me = None
        self.nodes, self.channels, self.sent = {}, {}, {}
        self.privacy = {}  # each channel's: open, public or private (mesh.privacy); never its key
        self.setup = {}    # the radio's: region, preset, hops, role, firmware (Settings, This radio)
        self.quiet = {}    # ports that didn't answer: when
        self.stopping = False

    # ---- the client side ----

    def start(self):
        threading.Thread(target=self.run, name="mesh-radio", daemon=True).start()
        return self

    def stop(self):
        self.stopping = True

    def snapshot(self):
        with self.cond:
            return {"seq": self.seq, "connected": self.connected, "problem": self.problem,
                    "device": self.link.name if self.link else None,
                    "me": mesh.node_id(self.me) if self.me is not None else None,
                    "channels": [{"index": i, "name": n, "privacy": self.privacy.get(i)} for i, n in sorted(self.channels.items())],
                    "radio": dict(self.setup),
                    "nodes": sorted((self.public(n) for n in self.nodes.values()), key=lambda n: -(n.get("last_heard") or 0))}

    def wait(self, after, timeout=25):
        """The events after `after`, waiting up to `timeout` seconds for one. "reset" when some were missed."""
        with self.cond:
            self.cond.wait_for(lambda: self.seq > after, timeout)
            missed = bool(self.events) and after < self.events[0]["seq"] - 1
            return {"seq": self.seq, "reset": missed, "events": [e for e in self.events if e["seq"] > after]}

    def send_text(self, words, channel=0, to=None, reply_id=None):
        words = words.strip()
        if not words:
            raise ValueError("nothing to send")
        if len(words.encode()) > mesh.MOST_TEXT:
            raise ValueError("too long: %d bytes, at most %d" % (len(words.encode()), mesh.MOST_TEXT))
        dest = mesh.BROADCAST if to in (None, "", "all") else int(str(to).lstrip("!"), 16)
        with self.cond:
            if not self.connected:
                raise RuntimeError("the radio isn't connected" + (": " + self.problem if self.problem else ""))
            if channel not in self.channels:
                raise ValueError("no channel %s on this radio" % channel)
            link = self.link
        pid = mesh.new_id()
        message = {"id": pid, "time": time.time(), "from": mesh.node_id(self.me), "from_name": self.name_of(self.me),
                   "to": mesh.node_id(dest), "to_name": None if dest == mesh.BROADCAST else self.name_of(dest),
                   "channel": channel, "channel_name": self.channels[channel], "text": words, "mine": True,
                   "status": "sending", "reply_id": reply_id}
        with self.write_lock:
            link.write(mesh.frame(mesh.text_packet(words, dest, channel, pid, reply_id)))
        with self.cond:
            self.sent[pid] = message
            if len(self.sent) > 200:
                self.sent.pop(next(iter(self.sent)))
        self.keep(message)
        self.emit("message", message=message)
        return message

    # ---- the radio side ----

    def run(self):
        while not self.stopping:
            now = time.time()
            try:
                link = open_link(self.device, skip={p for p, t in self.quiet.items() if now - t < QUIET})
            except (OSError, ValueError, StopIteration) as e:
                self.down(str(e))
                time.sleep(RETRY)
                continue
            with self.cond:
                self.link, self.problem = link, "asking the radio"
            self.log("mesh: radio on " + link.name)
            try:
                self.session(link)
            except NoAnswer as e:
                self.quiet[link.name] = time.time()  # not a radio, or not ready: the other ports first
                self.down(str(e))
            except OSError as e:
                self.down(str(e) or "the line dropped")
            finally:
                link.close()
            time.sleep(RETRY)

    def down(self, why):
        with self.cond:
            was = self.connected
            self.connected, self.problem, self.link = False, why, None
        if was and not self.stopping:
            self.log("mesh: radio lost: " + why)
            self.emit("link", connected=False, problem=why)

    def session(self, link):
        with self.cond:  # this radio's own, not the one plugged in before
            self.channels, self.privacy, self.setup, self.me = {}, {}, {}, None
        frames = mesh.Deframer()
        nonce = mesh.new_id() & 0x7FFFFFFF
        with self.write_lock:
            link.write(mesh.frame(mesh.want_config(nonce)))
        asked = beat = time.time()
        heard = False
        while not self.stopping:
            for raw in frames.feed(link.read(0.5)):
                heard = True
                try:
                    said = mesh.from_radio(raw)
                except (ValueError, IndexError):
                    continue  # a frame we can't read: skip it, the next one will do
                if said["kind"] == "rebooted":
                    raise OSError("the radio restarted")
                self.handle(said, nonce)
            now = time.time()
            if not heard and now - asked > ANSWER:
                raise NoAnswer("%s doesn't answer as a Meshtastic radio" % link.name.rsplit("/", 1)[-1])
            if now - beat > BEAT:
                with self.write_lock:
                    link.write(mesh.frame(mesh.heartbeat()))
                beat = now

    def handle(self, said, nonce):
        kind = said["kind"]
        if kind == "me":
            with self.cond:
                self.me = said["num"]
        elif kind == "node":
            self.update_node(said["num"], {k: v for k, v in said.items() if k not in ("kind", "num") and v is not None}, quiet=not self.connected)
        elif kind == "channel":
            with self.cond:
                if said["role"]:
                    self.channels[said["index"]] = said["name"] or ("Primary" if said["role"] == 1 else "Channel %d" % said["index"])
                    self.privacy[said["index"]] = said["privacy"]
                else:
                    self.channels.pop(said["index"], None)
                    self.privacy.pop(said["index"], None)
        elif kind in ("config", "metadata"):
            with self.cond:
                self.setup.update({k: v for k, v in said.items() if k != "kind" and v is not None})
        elif kind == "ready" and said["nonce"] == nonce:
            with self.cond:
                self.connected, self.problem = True, None
            self.log("mesh: ready, %d nodes, channels %s" % (len(self.nodes), ", ".join(self.channels.values())))
            self.emit("link", connected=True, state=self.snapshot())
        elif kind == "packet":
            self.packet(said)

    def packet(self, p):
        when = time.time()  # the board's clock (set from the network); a radio without GPS or phone may not know the time
        if p["port"] is None:
            return  # still encrypted: a channel this radio has no key for
        heard = {"last_heard": int(when)}
        if p["snr"] is not None and p["from"] != self.me:
            heard["snr"] = round(p["snr"], 1)
        if p["hop_start"] is not None and p["hop_limit"] is not None:
            heard["hops"] = p["hop_start"] - p["hop_limit"]
        port = p["port"]
        if port == mesh.TEXT:
            self.update_node(p["from"], heard, quiet=True)
            message = {"id": p["id"], "time": when, "from": mesh.node_id(p["from"]), "from_name": self.name_of(p["from"]),
                       "to": mesh.node_id(p["to"]), "to_name": None if p["to"] == mesh.BROADCAST else self.name_of(p["to"]),
                       "channel": p["channel"], "channel_name": self.channels.get(p["channel"], "Channel %d" % p["channel"]),
                       "text": p["payload"].decode("utf-8", "replace"), "mine": False, "snr": heard.get("snr"),
                       "rssi": p["rssi"], "hops": heard.get("hops"), "reply_id": p.get("reply_id"), "emoji": p.get("emoji")}
            self.keep(message)
            self.emit("message", message=message)
        elif port == mesh.ROUTING:
            self.ack(p)
            if p["from"] != self.me:  # a receipt is the node heard too
                self.update_node(p["from"], heard, quiet=True)
        elif port == mesh.NODEINFO:
            self.update_node(p["from"], {**heard, **{k: v for k, v in mesh.user(p["payload"]).items() if v}})
        elif port == mesh.POSITION:
            self.update_node(p["from"], {**heard, "position": mesh.position(p["payload"])})
        elif port == mesh.TELEMETRY:
            level = mesh.battery(p["payload"])
            self.update_node(p["from"], {**heard, **({"battery": level} if level is not None else {})})
        elif p["from"] != self.me:
            self.update_node(p["from"], heard, quiet=True)

    def ack(self, p):
        """What became of a message we sent: heard by the mesh, delivered to the one it was for, or failed."""
        with self.cond:
            message = self.sent.get(p.get("request_id"))
        if not message:
            return
        error = mesh.routing_error(p["payload"])
        if error:
            status = "failed: " + error
        elif message["to"] != mesh.node_id(mesh.BROADCAST) and p["from"] == int(message["to"][1:], 16):
            status = "delivered"
        elif message["status"] == "delivered":
            return
        else:
            status = "heard"
        if status == message["status"]:
            return
        message["status"] = status
        if self.archive:
            self.archive.add({"id": message["id"], "status": status}, when=message["time"])
        self.emit("status", id=message["id"], status=status)

    # ---- the book-keeping ----

    def update_node(self, num, fields, quiet=False):
        with self.cond:
            node = self.nodes.setdefault(num, {"num": num, "id": mesh.node_id(num)})
            node.update(fields)
            public = self.public(node)
        if not quiet:
            self.emit("node", node=public)

    def public(self, node):
        out = {k: v for k, v in node.items() if k != "num"}
        out["me"] = node["num"] == self.me
        out.setdefault("id", mesh.node_id(node["num"]))
        return out

    def name_of(self, num):
        node = self.nodes.get(num)
        return (node.get("long") or node.get("short")) if node else None

    def keep(self, message):
        if self.archive:
            try:
                self.archive.add(message)
            except OSError as e:
                self.log("mesh: not archived: %s" % e)

    def emit(self, kind, **data):
        with self.cond:
            self.seq += 1
            self.events.append({"seq": self.seq, "type": kind, **data})
            self.cond.notify_all()
