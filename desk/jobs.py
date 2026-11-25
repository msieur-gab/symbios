"""jobs: the board's limits for heavy work, read from desk.conf, so each board gets its own (Gab, 2026-11-22: "do the
job limits per board"; "It's just different approaches, and say that we support different boards").

Two kinds of work run under them, through `systemd-run --user`:
  job   a memo transcribed, a document embedded (voice.py): one at a time, killed at its ceiling, never swapped
  ask   the Ask service (ask.py): MiniLM kept loaded beside the server

desk.conf lines (the defaults are the Orange Pi Zero 2W's, measured on 2026-10-21 and 23 Oct):
  job_memory_high = 600M       above it the job is slowed (squeezed, kept alive)
  job_memory_max = 800M        the ceiling: a job that reaches it is stopped, the desk carries on
  job_cpu = 200%               a CPU quota (here 2 of the 4 cores), or none
  job_cores =                  the cores it may run on (e.g. 1-2), where a quota can't hold; empty: any
  ask_memory_high = 200M
  ask_memory_max = 300M
  ask_cpu = 200%
  ask_cores =
  speech_piece_seconds = 30    the longest piece of speech read at once: memory grows with it
  speech_chunk_seconds = 60    a memo is read in chunks of about this long, a fresh run of the model each: one run's
                               memory climbs with what it reads and never comes down (24 Nov)

What a board's systemd can't do is left out rather than refused: `CPUWeight=idle` came with systemd 250, and Ubuntu
22.04's 249 refuses the whole job over it (the Luckfox Lyra, 2026-11-22); `nice` keeps the job behind the desk there.
On the Lyra (464 MB, swap on the SD card, 3 cores): job 300M / 360M, ask 150M / 200M, pieces of 20 s; its kernel
has no CPU quota (no cpu.max: CFS bandwidth left out), so the jobs and Ask are held to cores 1 and 2 instead, core 0
left to the desk and TermNL (Gab, 23 Nov: "constrained on 2 cores"); 30 s of
unbroken speech needs ~370 MB and is stopped (brain: knowledge/hardware/luckfox-lyra-zero-w.md).
"""
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULTS = {"job_memory_high": "600M", "job_memory_max": "800M", "job_cpu": "200%",
            "ask_memory_high": "200M", "ask_memory_max": "300M", "ask_cpu": "200%", "speech_piece_seconds": "30",
            "speech_chunk_seconds": "60", "job_cores": "", "ask_cores": ""}


def read(path=os.path.join(HERE, "desk.conf")):
    """desk.conf's "name = value" lines (as server.py reads them), only the ones named in DEFAULTS."""
    found = {}
    try:
        with open(path) as f:
            for line in f:
                name, _, value = line.partition("=")
                if value and not name.strip().startswith("#") and name.strip() in DEFAULTS:
                    found[name.strip()] = value.split("#")[0].strip()
    except OSError:
        pass
    return {**DEFAULTS, **found}


def systemd_version():
    try:
        out = subprocess.run(["systemctl", "--version"], capture_output=True, text=True, timeout=10).stdout
        return int(re.search(r"systemd (\d+)", out).group(1))
    except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
        return 0


SETTINGS = read()
IDLE = systemd_version() >= 250  # CPUWeight=idle: systemd 250 and later
SPEECH_PIECE = int(SETTINGS["speech_piece_seconds"])
SPEECH_CHUNK = int(SETTINGS["speech_chunk_seconds"])


def limits(kind):
    """The -p properties for systemd-run, for "job" or "ask"."""
    s = SETTINGS
    out = ["-p", "MemoryHigh=" + s[kind + "_memory_high"], "-p", "MemoryMax=" + s[kind + "_memory_max"], "-p", "MemorySwapMax=0"]
    if s[kind + "_cpu"] not in ("", "none"):
        out += ["-p", "CPUQuota=" + s[kind + "_cpu"]]
    if s[kind + "_cores"]:
        out += ["-p", "CPUAffinity=" + s[kind + "_cores"]]
    if IDLE:
        out += ["-p", "CPUWeight=idle"]
    return out
