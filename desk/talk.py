"""TermNL, the desk's brain for what is said to it: loaded inside this server from its folder, or its own service
below the desk on a local socket (SymbiOS). And Ask: the articles and memos about a question (ask.py)."""
import json
import os
import re
import socket
import sys
import time
from urllib.parse import quote

import config

# The same for TermNL, which runs its skills' commands on this device itself: the ones the page does
# (commands.py, FORMS) come back to it instead.
SCREEN = re.compile(r"^(xdg-open|x-terminal-emulator|mousepad|mpc|setsid) |^pkill -x |^pactl set-sink-(volume|mute) |^brightnessctl set "
                    r"|^systemd-run ")


def asked(question):
    """A question to the articles and memos → {best, floor, results}: passed to the Ask service (ask.py), which
    keeps MiniLM loaded so this server never does. Started again if it has stopped; waited for while it loads."""
    import ask
    import urllib.error
    import urllib.request
    for again in (True, False):
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/ask?q=%s" % (ask.PORT, quote(question[:300])), timeout=20) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, ConnectionError, TimeoutError, ValueError):
            if not again or not (ask.running() or ask.start(config.HOME)):
                raise RuntimeError("asking isn't available on this device (no MiniLM in ~/.models/compare)"
                                   if not os.path.isfile(os.path.join(ask.embed.MODEL, "model_quantized.onnx"))
                                   else "the Ask service didn't answer; try again in a moment")
            time.sleep(3)  # it loads the model and the library


def talk(folder):
    """TermNL from its folder, loaded once, working in the desk's home. What --allow leaves out it only
    simulates: without files, the skills that make, move or rename; without power, those needing admin rights.
    Its own settings.md can simulate more. What it doesn't understand can be answered by the articles and memos.
    On the board, its Wi-Fi goes through desk-wifi, the one way allowed to scan and join there (netplan keeps
    wpa_supplicant to root): the password on standard input, what desk-wifi answers shown when joining fails."""
    sys.path.insert(0, folder)
    from termnl.server import TermNL
    wifi, said = "/usr/local/sbin/desk-wifi", os.path.join(config.HERE, "board", "desk-wifi-said")
    lent = {"show wifi": "iw dev wlan0 link; sudo -n %s scan" % wifi,
            # desk-wifi keeps a network, and the board uses whichever known one is in range: said as it is
            "connect wifi": {"command": "sudo -n %s add {network} | %s {network}" % (wifi, said),
                             "replies": {"done": "{output}", "approve": "Save {network} on the board? It joins the known network in range."}},
            # the desk restarts itself through systemd, 2 s later, so the answer gets out first (said by restart-service);
            # other services as before
            "restart service": "bash -c 'if [ \"$1\" = desk ]; then sudo -n /usr/bin/systemd-run --on-active=2 /usr/bin/systemctl restart desk"
                               " >/dev/null; else systemctl restart \"$1\"; fi' _ {name}",
            } if os.path.exists(wifi) else {}
    t = TermNL(home=config.HOME, screen=lambda command: bool(SCREEN.match(command)), doc=asked, commands=lent)
    try:
        from termnl.server import own  # what the page's screen holds, checked as TermNL's own API checks it
        said = t.say
        t.say = lambda text, session, shown=None: said(text, session, None, own(shown or {}))
    except ImportError:  # a TermNL from before the desk named its apps: they are only left unknown
        pass
    def group(s):
        return "power" if s["admin"] else "files" if s["command"].split(" ")[0] in ("mkdir", "touch", "mv") else None
    t.also_simulated = {s["does"] for s in t.lang["skills"] if group(s) and group(s) not in config.ALLOWED}

    def reset(session):
        with t.lock:
            t.sessions.pop(session, None)
    t.reset = reset
    return t


class Below:
    """TermNL as SymbiOS's foundation: its own service, below the desk, reached on its local socket (no network
    port). Each sentence says what this desk's screen does itself (SCREEN), handed back as "screen" instead of run
    on the board; TermNL's own settings, the commands the board lends it and its documents (Ask) are its own."""
    SCREEN = ["xdg-open ", "x-terminal-emulator ", "mousepad ", "mpc ", "setsid ", "pkill -x ", "pactl set-sink-volume ",
              "pactl set-sink-mute ", "brightnessctl set ", "systemd-run "]

    def __init__(self, path):
        self.path = path

    def post(self, route, body):
        import http.client

        class Local(http.client.HTTPConnection):
            def connect(c):
                c.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                c.sock.settimeout(c.timeout)
                c.sock.connect(self.path)
        c = Local("termnl", timeout=120)
        c.request("POST", route, json.dumps(body), {"Content-Type": "application/json"})
        return json.loads(c.getresponse().read() or b"{}")

    def say(self, text, session, shown=None):
        """shown: what the page's screen holds, {"apps", "running"}: its own apps, known to TermNL for this sentence"""
        return self.post("/api/say", {"text": text, "session": session, "screen": self.SCREEN, **(shown or {})})

    def reset(self, session):
        self.post("/api/reset", {"session": session})


class TalkRoutes:
    """The server's routes for TermNL and Ask (mixed into its handler)."""

    def ask(self, question):
        try:
            return self.send(asked(question))
        except RuntimeError as e:
            return self.fail(503, str(e))

    def say(self, body, reset=False):
        """A sentence for TermNL → its reply: what it says, a table or chips, and the command with what became
        of it ("screen": the page does it). A reset starts a new conversation."""
        try:
            session, text = str(body["session"])[:64], str(body.get("text", "")).strip()[:500]
        except (KeyError, AttributeError, TypeError):
            return self.fail(400, "expected {\"text\": \"…\", \"session\": \"…\"}")
        if reset:
            config.TALK.reset(session)
            return self.send({"reset": True})
        if not text:
            return self.fail(400, "say something")
        try:
            shown = {k: body[k] for k in ("apps", "running") if isinstance(body.get(k), list)}
            return self.send(config.TALK.say(text, session, shown))
        except Exception as e:  # a bug in TermNL never takes the desk down
            sys.stderr.write("TermNL: %r\n" % e)
            return self.fail(500, "TermNL couldn't answer that")
