"""The radio without the desk, to try it (from the desk's folder): python3 -m mesh [--device auto] nodes | listen | send "words" [--channel 1] [--to !id]"""
import argparse
import datetime
import os
import sys
import time

from .archive import Archive
from .radio import Radio


def main():
    ap = argparse.ArgumentParser(prog="mesh", description=__doc__)
    ap.add_argument("--device", default="auto", help="auto, usb, serial, /dev/ttyACM0 or tcp:host[:port]")
    ap.add_argument("--folder", help="keep the messages heard in this folder, by day")
    sub = ap.add_subparsers(dest="do", required=True)
    sub.add_parser("nodes", help="the radio's channels and the nodes it knows")
    sub.add_parser("listen", help="print messages as they come (Ctrl-C to stop)")
    send = sub.add_parser("send", help="send one text message")
    send.add_argument("text")
    send.add_argument("--channel", type=int, default=0)
    send.add_argument("--to", help="a node id (!b2df9083) for a direct message")
    args = ap.parse_args()

    global RADIO
    radio = RADIO = Radio(args.device, Archive(os.path.expanduser(args.folder)) if args.folder else None,
                  log=lambda line: print(line, file=sys.stderr)).start()
    ready = time.time() + 30
    while not radio.connected and time.time() < ready:
        time.sleep(0.2)
    if not radio.connected:
        sys.exit("no radio: %s" % radio.problem)
    state = radio.snapshot()
    if args.do == "nodes":
        print("me", state["me"], "on", state["device"])
        for c in state["channels"]:
            print("channel %d  %s" % (c["index"], c["name"]))
        for n in state["nodes"]:
            seen = datetime.datetime.fromtimestamp(n["last_heard"]).strftime("%m-%d %H:%M") if n.get("last_heard") else "never"
            print("%s  %-5s %-24s heard %s  hops %s  snr %s" % (n["id"], n.get("short") or "", (n.get("long") or "")[:24], seen, n.get("hops", "?"), n.get("snr", "?")))
        return
    if args.do == "send":
        sent = radio.send_text(args.text, args.channel, args.to)
        print("sent", "%08x" % sent["id"], "on", sent["channel_name"])
        end, after = time.time() + 30, state["seq"]
        while time.time() < end:
            got = radio.wait(after, 5)
            after = got["seq"]
            for e in got["events"]:
                if e["type"] == "status" and e["id"] == sent["id"]:
                    print(e["status"])
                    if e["status"] != "heard" or not args.to:
                        return
        return
    after = state["seq"]
    try:
        while True:
            got = radio.wait(after)
            after = got["seq"]
            for e in got["events"]:
                if e["type"] == "message":
                    m = e["message"]
                    print("%s [%s] %s: %s" % (time.strftime("%H:%M", time.localtime(m["time"])), m["channel_name"], m["from_name"] or m["from"], m["text"]))
                elif e["type"] == "link" and not e["connected"]:
                    print("-- radio lost:", e["problem"])
    except KeyboardInterrupt:
        pass


try:
    main()
finally:
    RADIO.stop() if "RADIO" in globals() else None
