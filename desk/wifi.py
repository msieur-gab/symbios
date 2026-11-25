"""wifi: where the device is, the networks it knows, what is in range; adding and forgetting one.

On a board the work is the board's own helper, run as root through sudo: SymbiOS's symbios-wifi (installed with
TermNL, the same on the Orange Pi and the Lyra, netplan or wpa_supplicant behind it), or the desk's older board/desk-wifi
on a board set up by the desk's own install.sh; its answers are kept as they are (Gab, 23 Nov: "how I can add new Wi-Fi
to the board"; the desk looked only for desk-wifi, which SymbiOS never installs, so on SymbiOS it could only look). On
the laptop there is no helper, and the desk only looks (NetworkManager's nmcli, read-only): nothing here changes the
laptop's WiFi. A device with neither says where it is, from iw and ip.

Every answer: {"ssid", "ip", "known": [{"ssid", "ours"}], "readonly"} or {"networks": [{"ssid", "signal", "secure"}]}.
"""
import json
import os
import re
import subprocess

HELPER = next((h for h in ("/usr/local/sbin/symbios-wifi", "/usr/local/sbin/desk-wifi") if os.path.exists(h)),
              "/usr/local/sbin/symbios-wifi")


def run(*cmd, data=None, wait=20):
    try:
        return subprocess.run(cmd, input=data, capture_output=True, text=True, timeout=wait).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def board():
    return os.path.exists(HELPER)


def helper(act, ssid="", password=""):
    out = run("sudo", "-n", HELPER, act, *([ssid] if ssid else []), data=password, wait=120)
    try:
        return json.loads(out)
    except ValueError:
        return {"error": "the board's WiFi helper didn't answer"}


def fields(line):
    """One line of nmcli -t: fields split on ':' that isn't escaped."""
    return [f.replace("\\:", ":") for f in re.split(r"(?<!\\):", line)]


def status():
    if board():
        return {**helper("status"), "readonly": False}
    if not run("nmcli", "-v"):  # no NetworkManager (the Lyra): where it is, from the kernel's own tools
        return bare()
    ssid = next((f[1] for f in map(fields, run("nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi").splitlines()) if f[0] == "yes"), None)
    device = next((f[0] for f in map(fields, run("nmcli", "-t", "-f", "DEVICE,TYPE", "dev").splitlines()) if len(f) > 1 and f[1] == "wifi"), None)
    ip = re.search(r"inet ([\d.]+)", run("ip", "-4", "-o", "addr", "show", device)) if device else None
    known = [f[0] for f in map(fields, run("nmcli", "-t", "-f", "NAME,TYPE", "connection", "show").splitlines())
             if len(f) > 1 and f[1] == "802-11-wireless"]
    return {"ssid": ssid or None, "ip": ip.group(1) if ip and ssid else None, "readonly": True,
            "known": [{"ssid": s, "ours": False} for s in sorted(known, key=str.lower)]}


def bare():
    """Where the device is when neither the board's helper nor NetworkManager is there: iw and ip, read-only."""
    for dev in re.findall(r"Interface (\S+)", run("iw", "dev")):
        link = re.search(r"SSID: (.+)", run("iw", "dev", dev, "link"))
        if link:
            ip = re.search(r"inet ([\d.]+)", run("ip", "-4", "-o", "addr", "show", dev))
            return {"ssid": link.group(1).strip(), "ip": ip.group(1) if ip else None, "readonly": True, "known": []}
    return {"ssid": None, "ip": None, "readonly": True, "known": []}


def scan():
    if board():
        return helper("scan")
    best = {}
    for f in map(fields, run("nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list").splitlines()):
        if len(f) < 3 or not f[0]:
            continue
        signal = int(f[1] or 0) / 2 - 100  # nmcli's 0–100 → about the dBm the board's helper gives
        if f[0] not in best or signal > best[f[0]]["signal"]:
            best[f[0]] = {"ssid": f[0], "signal": signal, "secure": f[2] not in ("", "--")}
    return {"networks": sorted(best.values(), key=lambda n: -n["signal"])}


def change(act, ssid, password=""):
    if not board():
        return {**status(), "error": "on the laptop the desk only looks: networks are added on the board"}
    return {**helper(act, ssid, password), "readonly": False}
