"""Mesh's routes, the desk's own (server.py answers them before any add-on's). Under /api/, so the lock covers them.
  GET  /api/mesh/state               connected or not, the radio's channels and the nodes it knows
  GET  /api/mesh/messages?day=…      a day's messages (today when no day), and the days kept
  GET  /api/mesh/wait?after=N        what changed after event N (waits up to 25 s)
  POST /api/mesh/send                {"text", "channel"?, "to"?, "reply_id"?}
Settings from desk.conf: mesh_device (auto, usb, /dev/ttyACM0, tcp:host), mesh_folder (in the desk's home: Mesh).
"""
import os
import sys
import time

from .archive import Archive
from .radio import Radio

class Mesh:

    def __init__(self, home, conf=None):
        conf = conf or {}
        self.archive = Archive(os.path.join(home, conf.get("mesh_folder", "Mesh")))
        self.device = conf.get("mesh_device", "auto")
        self.radio = Radio(self.device, self.archive, log=lambda line: sys.stderr.write(line + "\n"))

    def start(self):
        if self.device == "off":  # a board told to leave its radio alone (desk.conf, or server.py --mesh off)
            self.radio.problem = "off on this board (mesh_device = off)"
            return
        self.radio.start()

    def summary(self):
        """The radio Mesh is talking to, for the quick panel: its node's name and its port, or None."""
        s = self.radio.snapshot()
        if not s["connected"]:
            return None
        me = next((n for n in s["nodes"] if n.get("me")), {})
        return {"name": me.get("long") or me.get("short") or s["me"], "short": me.get("short"), "device": s["device"]}

    def handle(self, method, path, query, body):
        if not path.startswith("/api/mesh/"):
            return None
        route = method + " " + path[len("/api/mesh/"):]
        if route == "GET state":
            return 200, self.radio.snapshot()
        if route == "GET messages":
            day = query.get("day") or self.archive.day_of(time.time())
            try:
                return 200, {"day": day, "days": self.archive.days(), "messages": self.archive.read(day)}
            except ValueError as e:
                return 400, {"error": str(e)}
        if route == "GET wait":
            try:
                after = int(query.get("after", "0"))
            except ValueError:
                return 400, {"error": "after is a number"}
            return 200, self.radio.wait(after, timeout=25)
        if route == "POST send":
            if not isinstance(body, dict) or not isinstance(body.get("text"), str):
                return 400, {"error": "expected {\"text\": \"…\"}"}
            try:
                return 200, self.radio.send_text(body["text"], int(body.get("channel") or 0), body.get("to"), body.get("reply_id"))
            except ValueError as e:
                return 422, {"error": str(e)}
            except RuntimeError as e:
                return 503, {"error": str(e)}
            except OSError as e:
                return 503, {"error": "the radio didn't take it: %s" % e}
        return 404, {"error": "not found"}

