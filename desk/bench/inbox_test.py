#!/usr/bin/env python3
"""The inbox under load, on the board: what happens when files of every kind, links and recordings
arrive together. Run from the laptop:

    python3 bench/inbox_test.py gab@10.55.0.1 "../desk/voice memo/"*.m4a

A second copy of the desk server is started on the board from ~/desk, with --home ~/inbox-test and
port 8899, so the real desk, its ~/Inbox, ~/Memos and ~/Articles are never touched. A sampler writes
the board's free memory and load every second. At the end both are stopped, ~/inbox-test is kept
for a look, and the results are written to bench/results/inbox-<time>.md.

Scenarios: one link at rest; five recordings at once; a link during a transcription; a mix of kinds
at once; the same file twice; an upload cut short; the server restarted mid-queue. The sampler also
counts the heavy jobs running (ffmpeg, sherpa-onnx) and those waiting for the board's lock.
"""
import datetime
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote

PORT = 8899
LINKS = ["https://en.wikipedia.org/wiki/Permacomputing",
         "https://en.wikipedia.org/wiki/Orange_Pi",
         "https://en.wikipedia.org/wiki/Speech_recognition"]
PAYWALL = "https://time.com/7331883/how-ai-will-transform-democracy/"  # 406 to anything not a browser (2026-10-14)

SAMPLER = """while :; do
  echo "$(date +%s.%N) $(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print int((t-a)/1024)}' /proc/meminfo) $(cut -d' ' -f1 /proc/loadavg) $(pgrep -cf '^(/[^ ]*/sherpa-onnx-vad-with-offline-asr|ffmpeg -nostdin)') $(pgrep -cf '^flock .*desk-heavy')"
  sleep 1
done"""

# Run on the board through `python3 -`: every file under ~/inbox-test, and each memo's status.
STATE = r"""
import json, os, re
home = os.path.expanduser("~/inbox-test")
out = {"files": [], "memos": {}}
for root, dirs, files in os.walk(home):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), home)
        out["files"].append(rel)
        if f == "transcript.md":
            head = open(os.path.join(root, f), encoding="utf-8").read(800)
            m = dict(re.findall(r"^(\w+): (.*)$", head.split("\n---", 1)[0], re.M))
            out["memos"][os.path.basename(root)] = {"status": m.get("status"), "source": m.get("source"),
                                                    "duration": m.get("duration")}
print(json.dumps(out))
"""


class Board:
    def __init__(self, target):
        self.target = target
        self.host = target.split("@")[-1]

    def ssh(self, command, stdin=None, timeout=60):
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", self.target, command],
                           input=stdin, capture_output=True, text=True, timeout=timeout)
        return r.stdout

    def state(self):
        return json.loads(self.ssh("python3 -", STATE))

    def start(self, fresh=True):
        if fresh:
            self.ssh("rm -rf ~/inbox-test && mkdir -p ~/inbox-test")
        self.ssh("cd ~/desk && setsid -f python3 -u server.py --home ~/inbox-test --port %d --allow files,status "
                 "--shell off >> ~/inbox-test.log 2>&1 < /dev/null" % PORT)
        for _ in range(40):
            try:
                self.get("/api/hello")
                return
            except OSError:
                time.sleep(0.5)
        sys.exit("the test server didn't answer on port %d (see ~/inbox-test.log on the board)" % PORT)

    def stop(self):
        self.ssh("pkill -f 'server.py --home /home/[^ ]*/inbox-test'; true")

    def sampler(self, on):
        if on:
            self.ssh("cat > ~/inbox-test-sampler.sh", SAMPLER)
            self.ssh("setsid -f sh ~/inbox-test-sampler.sh > ~/inbox-test-samples.log 2>&1 < /dev/null")
        else:
            self.ssh("pkill -f '[i]nbox-test-sampler'; true")

    def samples(self):
        rows = []
        for line in self.ssh("cat ~/inbox-test-samples.log").splitlines():
            try:
                t, used, load, heavy, queued = line.split()
                rows.append((float(t), int(used), float(load), int(heavy), int(queued)))
            except ValueError:
                pass
        return rows

    def request(self, method, path, body=None, kind=None, timeout=300):
        req = urllib.request.Request("http://%s:%d%s" % (self.host, PORT, path), data=body, method=method)
        if kind:
            req.add_header("Content-Type", kind)
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                code, data = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, data = e.code, e.read()
        try:
            answer = json.loads(data)
        except ValueError:
            answer = data[:200].decode("utf-8", "replace")
        return {"code": code, "seconds": round(time.time() - t, 2), "answer": answer}

    def get(self, path):
        return self.request("GET", path, timeout=3)

    def drop(self, name, data, modified=None):
        # recordings say they come from the companion's recorder, so the rulebook makes them memos
        q = "/api/inbox?name=" + quote(name) + ("&modified=%d" % modified if modified else "")
        q += "&source=recorder" if name.lower().endswith((".m4a", ".webm", ".ogg")) else ""
        return self.request("POST", q, data, "application/octet-stream")

    def link(self, url):
        return self.request("POST", "/api/articles", json.dumps({"url": url}).encode(), "application/json")

    def wait_memos(self, count, limit=900):
        """Until `count` memos are done or failed; returns when each was first seen finished."""
        t0, seen = time.time(), {}
        while time.time() - t0 < limit:
            for name, m in self.state()["memos"].items():
                if m["status"] in ("done", "failed") and name not in seen:
                    seen[name] = (round(time.time() - t0), m["status"], m.get("duration"))
            if len(seen) >= count:
                break
            time.sleep(3)
        return seen

    def cut_upload(self, name):
        """Says 1 MB is coming, sends 1 KB, hangs up."""
        s = socket.create_connection((self.host, PORT), timeout=10)
        s.sendall(("POST /api/inbox?name=%s HTTP/1.1\r\nHost: x\r\nContent-Length: 1000000\r\n\r\n" % quote(name)).encode()
                  + b"x" * 1000)
        s.close()
        time.sleep(3)


def tiny_png():
    import struct
    import zlib

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    raw = b"".join(b"\0" + b"\x30\x60\x40" * 8 for _ in range(8))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def tiny_pdf():
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>"]
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += "%d 0 obj %s endobj\n" % (i, o)
    xref = len(out)
    out += "xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + "".join("%010d 00000 n \n" % o for o in offsets)
    return (out + "trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)).encode()


def window(samples, t0, t1):
    inside = [s for s in samples if t0 <= s[0] <= t1]
    if not inside:
        return "no samples"
    return "memory used up to %d MB, load up to %.2f, heavy jobs running at once up to %d" % (
        max(s[1] for s in inside), max(s[2] for s in inside), max(s[3] for s in inside))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    board, audio = Board(sys.argv[1]), [open(p, "rb").read() for p in sys.argv[2:]]
    # The inbox keeps the same bytes once, so a recording sent again here gets a few bytes more at its end
    unique = iter(range(1, 1000))
    again = lambda data: data + bytes(next(unique))  # noqa: E731
    recordings = [(again(audio[i % len(audio)]), "test-%d.m4a" % (i + 1)) for i in range(5)]
    report, marks = [], []

    def step(title, fn):
        print("·", title, flush=True)
        t0 = time.time()
        found = fn()
        marks.append((title, t0, time.time()))
        report.append((title, found))

    board.stop()
    board.sampler(True)
    board.start()
    time.sleep(3)

    step("1. One link, the board at rest", lambda: {"link": board.link(LINKS[0])})

    def five():
        sent = [board.drop(n, d) for d, n in recordings]
        return {"sent": sent, "finished (s after the last upload)": board.wait_memos(5)}
    step("2. Five recordings at once", five)

    def link_during():
        board.drop("test-busy.m4a", again(audio[0]))
        time.sleep(8)  # the transcription is under way
        busy = board.link(LINKS[1])
        board.wait_memos(6)
        return {"link while transcribing": busy}
    step("3. A link during a transcription", link_during)

    def mix():
        before = set(board.state()["files"])
        sent = {"audio": board.drop("mix.m4a", again(audio[-1])), "image": board.drop("mix.png", tiny_png()),
                "pdf": board.drop("mix.pdf", tiny_pdf()), "text": board.drop("mix.txt", b"a plain note\n"),
                "markdown": board.drop("mix.md", b"# A note\n\nWith a heading.\n"),
                "link": board.link(LINKS[2]), "paywalled link": board.link(PAYWALL)}
        board.wait_memos(7)
        return {"sent": sent, "new files, after the transcription": sorted(set(board.state()["files"]) - before)}
    step("4. A mix of kinds at once", mix)

    def twice():
        before = set(board.state()["files"])
        a, b = board.drop("twice.txt", b"same\n"), board.drop("twice.txt", b"same\n")
        c, d = board.drop("twice.m4a", audio[0]), board.drop("twice again.m4a", audio[0])
        board.wait_memos(8)
        return {"text, first": a, "text, second": b, "recording, first": c, "recording, second (another name)": d,
                "new files": sorted(set(board.state()["files"]) - before)}
    step("5. The same file twice", twice)

    def cut():
        board.cut_upload("cut.m4a")
        return {"files named cut, or half arrived": [f for f in board.state()["files"] if "cut" in f or "arriving" in f]}
    step("6. An upload cut short", cut)

    def restart():
        board.drop("restart-1.m4a", again(audio[0]))
        board.drop("restart-2.m4a", again(audio[0]))
        time.sleep(10)  # the first one is being transcribed
        before = board.state()["memos"]
        board.stop()
        time.sleep(3)
        board.start(fresh=False)
        done = board.wait_memos(10)
        return {"memos when stopped": {k: v["status"] for k, v in before.items()},
                "after the restart": {k: v[1] for k, v in done.items()}}
    step("7. The server restarted mid-queue", restart)

    final = board.state()
    board.stop()
    board.sampler(False)
    samples = board.samples()

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
    lines = ["# The inbox under load, %s" % stamp, "",
             "Board: `%s`. Test server on port %d with `--home ~/inbox-test`. "
             "Memory is the board's total in use (MemTotal − MemAvailable)." % (board.target, PORT), ""]
    for (title, found), (_, t0, t1) in zip(report, marks):
        lines += ["## " + title, "", "%d s; %s." % (t1 - t0, window(samples, t0, t1)), "",
                  "```json", json.dumps(found, indent=1, ensure_ascii=False), "```", ""]
    lines += ["## Everything left in ~/inbox-test", "", "```", *sorted(final["files"]), "```", "",
              "## Memos", "", "```json", json.dumps(final["memos"], indent=1, ensure_ascii=False), "```", ""]
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
    os.makedirs(here, exist_ok=True)
    path = os.path.join(here, "inbox-%s.md" % stamp.replace(" ", "-"))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(path)


if __name__ == "__main__":
    main()
