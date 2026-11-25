"""The person's preferences, kept on the board so every screen showing the desk is the same desk (Gab, 24 Nov: Settings,
"the place where we can define which application is making it to the app launcher bar ... and perhaps other things").
One JSON file in the home: ~/.config/desk/prefs.json, written whole each time (a new file, then moved in place).

GET  /api/prefs              every preference: {"apps": {"memos": {"dock": true}}, ...}
POST /api/prefs {key: value} each key set (null removes it); the answer is every preference again
"""
import json
import os
import threading

import config

MOST = 64 * 1024  # the whole file: far more than a person's preferences need
LOCK = threading.Lock()


def path():
    return os.path.join(config.HOME, ".config", "desk", "prefs.json")


def read():
    try:
        with open(path(), encoding="utf-8") as f:
            got = json.load(f)
        return got if isinstance(got, dict) else {}
    except (OSError, ValueError):
        return {}


def change(given):
    """Sets each key given (None removes it); refuses anything but an object of plain JSON, or one too large."""
    if not isinstance(given, dict) or not all(isinstance(k, str) and 0 < len(k) <= 64 for k in given):
        raise ValueError("expected {\"name\": value}")
    with LOCK:
        now = read()
        for k, v in given.items():
            if v is None:
                now.pop(k, None)
            else:
                now[k] = v
        text = json.dumps(now, ensure_ascii=False, indent=1)
        if len(text.encode()) > MOST:
            raise ValueError("too many preferences")
        os.makedirs(os.path.dirname(path()), exist_ok=True)
        new = path() + ".new"
        with open(new, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(new, path())
        return now
