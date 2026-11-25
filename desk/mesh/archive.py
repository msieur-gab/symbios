"""The conversation kept by day: one file per day, one line per message, written as it comes.

<folder>/2026-11-22.jsonl. A line is a message ({"id", "time", "from", …, "text"}) or, later in
the day, what became of one we sent ({"id", "status"}). Each line is flushed to the disk before
the next: a board unplugged loses at most the line being written. Days are the board's local days.
"""
import json
import os
import re
import threading
import time

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Archive:
    def __init__(self, folder):
        self.folder = folder
        self.lock = threading.Lock()

    def day_of(self, when):
        return time.strftime("%Y-%m-%d", time.localtime(when))

    def path(self, day):
        if not DAY.match(day):
            raise ValueError("a day is YYYY-MM-DD")
        return os.path.join(self.folder, day + ".jsonl")

    def add(self, line, when=None):
        day = self.day_of(when or line.get("time") or time.time())
        with self.lock:
            os.makedirs(self.folder, exist_ok=True)
            with open(self.path(day), "a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())

    def days(self):
        try:
            return sorted((n[:-6] for n in os.listdir(self.folder) if n.endswith(".jsonl") and DAY.match(n[:-6])), reverse=True)
        except FileNotFoundError:
            return []

    def read(self, day):
        """A day's messages in order, each with the last status heard for it."""
        messages, by_id = [], {}
        try:
            with open(self.path(day), encoding="utf-8") as f:
                for row in f:
                    try:
                        line = json.loads(row)
                    except ValueError:
                        continue  # a line cut by a power loss
                    if "text" in line:
                        messages.append(line)
                        by_id[line.get("id")] = line
                    elif line.get("id") in by_id and "status" in line:
                        by_id[line["id"]]["status"] = line["status"]
        except FileNotFoundError:
            pass
        return messages
