"""The commands the skills hand over (/api/exec): which forms may run, checked word by word, and a status
command's answer as a table row."""
import os
import re
import subprocess

import config
from status import status

# The commands the skills hand over, by group; --allow picks the groups that really run.
# PATH is something inside the home folder, TEXT is free text in single quotes. A command a
# skill sends that has no form here isn't run: a new skill command needs its line.
# Brightness, volume, timers and "open …" never get here: the page does those itself, on its
# own veil and its own player (device.js). Every host has keys for its real backlight and
# volume; the desk leaves those alone.
FORMS = {
    "files": [r"mkdir -p PATH", r"touch PATH", r"mv -n PATH PATH"],
    "status": [r"df -h /", r"uptime( -p)?", r"top -bn1", r"head -3", r"free -h", r"hostname -I", r"iwgetid -r",
               r"cat /sys/class/thermal/thermal_zone0/temp"],
    "power": [r"sudo systemctl (poweroff|reboot|suspend)"],
}
PLAIN = re.compile(r"[\w./:=%+,@~*-]")


def split(command):
    """The command as its parts between && and |, each a list of words, or an error. Single
    quotes hold free text; outside them only plain characters, $HOME and "plain words"."""
    parts, words, cur, i, n = [], [], "", 0, len(command)
    def end():
        nonlocal cur
        if cur:
            words.append(cur)
        cur = ""
    while i < n:
        c = command[i]
        if c == "'":
            j = command.find("'", i + 1)
            if j < 0:
                raise ValueError("a quote is left open")
            cur += command[i:j + 1]
            i = j + 1
        elif c == '"':
            j = command.find('"', i + 1)
            if j < 0 or not all(x == " " or PLAIN.match(x) for x in command[i + 1:j]):
                raise ValueError("double quotes may hold plain words only")
            cur += command[i:j + 1]
            i = j + 1
        elif command.startswith("\\'", i):
            cur += "\\'"
            i += 2
        elif command.startswith("$HOME", i):
            cur += "$HOME"
            i += 5
        elif command.startswith("&&", i) or c == "|":
            end()
            parts.append(words)
            words = []
            i += 2 if c == "&" else 1
        elif c == " ":
            end()
            i += 1
        elif PLAIN.match(c):
            cur += c
            i += 1
        else:
            raise ValueError("“%s” isn't allowed in a command" % c)
    end()
    parts.append(words)
    return parts


def shape(word):
    """A word as the forms name it: PATH inside the home folder, TEXT in quotes, else itself."""
    if re.match(r"\$HOME($|[/'])", word) and ".." not in re.split(r"[/']", word):
        return "PATH"
    if re.fullmatch(r"'[^']*'(\\''[^']*')*", word):
        return "TEXT"
    return word


def check(command, allowed):
    """(group, None) when the command may run, (group or None, reason) when it may not."""
    try:
        parts = split(command)
    except ValueError as e:
        return None, str(e)
    groups = []
    for words in parts:
        plain = " ".join(shape(w) for w in words)
        group = next((g for g, forms in FORMS.items() if any(re.fullmatch(f, plain) for f in forms)), None)
        if not group:
            return None, "“%s” isn't a command a skill declares" % " ".join(words)
        groups.append(group)
    off = [g for g in groups if g not in allowed]
    return groups[0], ("the “%s” commands are switched off on this device" % off[0]) if off else None


def size(n):
    return "%.1f GB" % (n / 2**30) if n >= 2**30 else "%d MB" % round(n / 2**20)


def span(seconds):
    d, h, m = seconds // 86400, seconds % 86400 // 3600, seconds % 3600 // 60
    words = [(d, "day"), (h, "hour"), (m, "minute")]
    return " ".join("%d %s%s" % (n, w, "" if n == 1 else "s") for n, w in words if n) or "less than a minute"


def said(command, out):
    """A status command's answer as a table row [what, value], instead of the raw output (which
    stays in the Terminal window). None when there is no row for the command."""
    st = status()
    if command.startswith("cat /sys/class/thermal"):
        t = st["temp"]
        if t is None:
            return ["Temperature", "no sensor on this board"]
        note = "fine" if t < 65 else "warm" if t < 80 else "too hot, the board slows itself down"
        return ["Temperature", "%.0f °C (%s; it slows down at 80 °C)" % (t, note)]
    if command == "free -h":
        m = st["memory"]
        return ["Memory", "%s in use, %s free, out of %s" % (size(m["used"]), size(m["total"] - m["used"]), size(m["total"]))]
    if command == "df -h /":
        d = st["disk"]
        return ["Disk", "%s in use, %s free, out of %s" % (size(d["used"]), size(d["total"] - d["used"]), size(d["total"]))]
    if command.startswith("uptime &&"):
        return ["Processor", "load %.2f on %d cores (%d%%)" % (st["load"][0], st["cores"], round(100 * st["load"][0] / st["cores"]))]
    if command == "uptime -p":
        return ["Running for", span(st["uptime"])]
    if command.startswith("hostname -I"):
        lines = out.strip().split("\n")
        ips = [ip for ip in lines[0].split() if ":" not in ip] if lines and lines[0] else []
        wifi = lines[1].strip() if len(lines) > 1 and lines[1].strip() else None
        if not ips:
            return ["Network", "not connected"]
        return ["Network", "%s, %s" % ("Wi-Fi “%s”" % wifi if wifi else "connected", " and ".join(ips))]
    return None


class CommandRoutes:
    """The server's /api/exec (mixed into its handler)."""

    def exec(self, body):
        try:
            command = body["command"].strip()
        except (KeyError, AttributeError, TypeError):
            return self.fail(400, "expected {\"command\": \"…\"}")
        group, why = check(command, config.ALLOWED)
        if why:
            # not run: the page shows it as simulated (group known) or refused (unknown program)
            return self.send({"ran": False, "group": group, "why": why})
        try:
            r = subprocess.run(["bash", "-c", command], cwd=config.HOME, env={**os.environ, "HOME": config.HOME},
                               capture_output=True, text=True, timeout=10)
            row = said(command, r.stdout) if group == "status" and r.returncode == 0 else None
            self.send({"ran": True, "group": group, "code": r.returncode, "out": r.stdout[-4000:], "err": r.stderr[-2000:], "row": row})
        except subprocess.TimeoutExpired:
            self.send({"ran": True, "group": group, "code": 124, "out": "", "err": "stopped after 10 seconds"})
