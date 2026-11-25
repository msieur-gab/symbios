"""The board's numbers for the Monitor, read from /proc and /sys."""
import os

import config


def status():
    """The board's numbers for the System window, read from /proc and /sys."""
    out = {"host": os.uname().nodename}
    try:
        out["model"] = open("/proc/device-tree/model").read().strip("\0\n")
    except OSError:
        out["model"] = os.uname().machine
    try:
        out["temp"] = round(int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000, 1)
    except (OSError, ValueError):
        out["temp"] = None
    mem = dict(line.split(":") for line in open("/proc/meminfo"))
    kb = lambda k: int(mem[k].split()[0])
    out["memory"] = {"used": (kb("MemTotal") - kb("MemAvailable")) * 1024, "total": kb("MemTotal") * 1024}
    d = os.statvfs(config.HOME)
    out["disk"] = {"used": (d.f_blocks - d.f_bfree) * d.f_frsize, "total": d.f_blocks * d.f_frsize}
    out["load"] = [float(x) for x in open("/proc/loadavg").read().split()[:3]]
    out["cores"] = os.cpu_count()
    out["uptime"] = int(float(open("/proc/uptime").read().split()[0]))
    return out
