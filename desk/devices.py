"""devices: what is connected, for the quick panel's tiles. Read-only, standard library and the system's own tools.

    bluetooth()   the adapter (on or off) and the devices paired and connected (bluetoothctl)
    volume()      the sound's level and whether it is muted, on the default output (PipeWire's wpctl, as v1)
    set_volume()  the level (0 to 100) and/or muted; the level is kept while muted
    mesh()        a Meshtastic node plugged in by USB: its maker's id is one of desk-meshtastic's
                  (mesh/link.py, VENDORS), read from /sys, so nothing is opened or sent. The name
                  is the board's USB name; the node's own (long and short) comes when desk-meshtastic talks to it
"""
import os
import re
import subprocess

from mesh.link import VENDORS  # noqa: E402  the makers of Meshtastic boards: Mesh's own list
USB = "/sys/bus/usb/devices"


def run(*cmd, wait=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=wait).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None


def bluetooth():
    show = run("bluetoothctl", "show")
    if not show or "Controller" not in show:
        return {"adapter": False, "on": False, "devices": []}
    devices = {}
    for line in (run("bluetoothctl", "devices", "Paired") or "").splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.+)", line.strip())
        if m:
            devices[m.group(1)] = {"name": m.group(2), "connected": False}
    for line in (run("bluetoothctl", "devices", "Connected") or "").splitlines():
        m = re.match(r"Device ([0-9A-F:]{17}) (.+)", line.strip())
        if m:
            devices.setdefault(m.group(1), {"name": m.group(2)})["connected"] = True
    return {"adapter": True, "on": bool(re.search(r"Powered: yes", show)),
            "devices": sorted(devices.values(), key=lambda d: (not d["connected"], d["name"].lower()))}


SINK = "@DEFAULT_AUDIO_SINK@"


def volume():
    out = run("wpctl", "get-volume", SINK)
    m = re.search(r"Volume:\s*([\d.]+)", out or "")
    if not m:
        return {"level": None}
    return {"level": round(float(m.group(1)) * 100), "muted": "MUTED" in out}


def set_volume(level=None, muted=None):
    """The level (0 to 100) and/or muted; muting keeps the level, so unmuting brings it back."""
    if level is not None:
        level = max(0, min(100, int(level)))
        run("wpctl", "set-volume", "-l", "1.0", SINK, "%.2f" % (level / 100))
        if level and muted is None:
            muted = False  # moving the slider up is wanting to hear
    if muted is not None:
        run("wpctl", "set-mute", SINK, "1" if muted else "0")
    return volume()


def read(path):
    try:
        return open(path).read().strip()
    except OSError:
        return ""


def drive_only(dev):
    """Whether a USB device offers a drive and no serial port: a board in its bootloader, for a firmware update."""
    classes = {read(os.path.join(USB, i, "bInterfaceClass")) for i in os.listdir(USB) if i.startswith(os.path.basename(dev) + ":")}
    return "08" in classes and not classes & {"02", "0a"}


def mesh():
    nodes = []
    for d in sorted(os.listdir(USB)) if os.path.isdir(USB) else []:
        vendor = read(os.path.join(USB, d, "idVendor"))
        try:
            vid = int(vendor, 16)
        except ValueError:
            continue
        if vid in VENDORS:
            nodes.append({"maker": read(os.path.join(USB, d, "manufacturer")) or VENDORS[vid],
                          "name": read(os.path.join(USB, d, "product")) or "a node",
                          "id": "%s:%s" % (vendor, read(os.path.join(USB, d, "idProduct"))),
                          # a board waiting for new firmware shows itself as a drive (mass storage), not a serial
                          # port: its USB name says nothing (a XIAO running Meshtastic calls itself "XIAO-BOOT")
                          "boot": drive_only(os.path.join(USB, d))})
    return {"nodes": nodes}
