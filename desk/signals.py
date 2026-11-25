"""signals: what happens on the desk, told to every screen as it happens, so lists update and Activity
shows the work without anyone reloading a page.

Two things are told. A change: a file placed by the inbox, a memo written, a deck made; each has a
number, and a screen asks for what came after the last number it has (GET /api/changes?after=N). The
answer waits until something happens (25 s at most), as /api/slides/now does. And the tasks: the heavy
work on the board, pending, running (with the time it is expected to take), done or failed; they come
with every answer, and Activity draws them.

A restarted desk numbers from 0 again, under a new boot time: a screen that sees another boot reloads
its lists once. A screen too far behind (more than KEPT changes) is told it missed some, and does the
same. Nothing is written to disk: the files themselves are the record, this only says they changed.

    publish("Memos", "2026-10-21 15-02 That's the beginning")   # a change in a folder
    task("memo:2026-10-21 15-02", "Voice memo 15:02", "running", expect=80)
"""
import threading
import time

KEPT = 200  # changes remembered for screens that were away a moment
GONE = 10   # seconds a finished task is still told, so every screen sees it end
BOOT = int(time.time())
CHANGED = threading.Condition()
CHANGES = []  # {"seq", "at", "folder", "name"}
TASKS = {}  # id → {"id", "name", "kind", "state", "since", "expect", "done", "ended"}
SEQ = 0
FORGOT = 0  # the number of the last change no longer kept


def publish(folder, name=""):
    """Something in a folder changed (relative to the home folder: "Memos", "Slides/Pitch")."""
    global SEQ, FORGOT
    with CHANGED:
        SEQ += 1
        CHANGES.append({"seq": SEQ, "at": time.time(), "folder": folder, "name": name})
        if len(CHANGES) > KEPT:
            FORGOT = CHANGES[-KEPT - 1]["seq"]
            del CHANGES[:-KEPT]
        CHANGED.notify_all()


def task(id, name, state, kind="", expect=None, done=None):
    """A heavy job's state: pending (waiting its turn), running (expect: the seconds it should take, or None; done:
    how much of it is done, 0 to 1, when the job itself tells it, as a memo's model does), done or failed. Each change
    is told like a file change, so screens hear it at once."""
    global SEQ
    with CHANGED:
        now = time.time()
        t = TASKS.get(id) or {"id": id, "name": name, "kind": kind, "since": now, "expect": None, "done": None,
                                  "ended": None}
        if t.get("state") == state and t["name"] == name and (expect is None or t["expect"] == expect) \
                and (done is None or t.get("done") == done):
            return  # nothing new to tell (the worker says "pending" again at each round)
        if state == "running" and t.get("state") != "running":
            t["since"] = now
        t.update(name=name, state=state, kind=kind or t["kind"])
        if expect is not None:
            t["expect"] = expect
        if done is not None:
            t["done"] = done
        if state in ("done", "failed"):
            t["ended"] = now
        TASKS[id] = t
        SEQ += 1
        CHANGED.notify_all()


def drop(id):
    """A task that won't run after all (its file is gone before its turn): no longer told."""
    global SEQ
    with CHANGED:
        if TASKS.pop(id, None):
            SEQ += 1
            CHANGED.notify_all()


def since(after, boot=None, wait=25.0):
    """What a screen hasn't heard: the changes after its number (all of them as missed when it heard
    another boot, or is too far behind), and the tasks as they are now."""
    with CHANGED:
        if boot == BOOT and after >= SEQ:
            CHANGED.wait_for(lambda: SEQ > after, timeout=wait)
        now = time.time()
        for id in [id for id, t in TASKS.items() if t["ended"] and now - t["ended"] > GONE]:
            del TASKS[id]
        missed = boot != BOOT or after < FORGOT
        return {"boot": BOOT, "seq": SEQ, "now": now, "missed": bool(missed),
                "changes": [] if missed else [c for c in CHANGES if c["seq"] > after],
                "tasks": sorted(TASKS.values(), key=lambda t: (t["state"] != "running", t["since"]))}
