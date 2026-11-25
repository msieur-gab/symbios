"""Add-ons: Python packages that bring the desk routes and a window of their own (desk-meshtastic is the first).

desk.conf names them: "addons = desk_meshtastic" (several, separated by spaces). Each package gives
addon(home, conf) -> an object with:
  name      its folder under /addons/, where its window's files are served from (web)
  app       its window: {"id", "name", "icon" (SVG), "x", "y", "w", "h", "module" (its JS, under /addons/<name>/)}
  web       the folder of those files
  start()   once, at the desk's start
  handle(method, path, query, body) -> (code, answer) | None   None when the route isn't its own
Its routes are under /api/, so the lock covers them like the desk's own. One that can't be
imported is said in the log and left out: the desk starts without it.
"""
import importlib
import os
import sys

LOADED = []


def load(names, home, conf):
    for name in names:
        try:
            addon = importlib.import_module(name).addon(home, conf)
            addon.start()
        except Exception as e:  # an add-on never stops the desk
            sys.stderr.write("addon %s left out: %s: %s\n" % (name, type(e).__name__, e))
            continue
        LOADED.append(addon)
        sys.stderr.write("addon %s: the %s window, routes under /api/%s/\n" % (name, addon.app["name"], addon.name))


def apps():
    return [a.app for a in LOADED]


def route(method, path, query, body):
    for a in LOADED:
        hit = a.handle(method, path, query, body)
        if hit is not None:
            return hit
    return None


def file(path):
    """/addons/<name>/<file>: the file, if it is inside that add-on's folder."""
    parts = path.split("/", 3)
    if len(parts) < 4:
        return None
    for a in LOADED:
        if a.name == parts[2]:
            root = os.path.realpath(a.web)
            full = os.path.realpath(os.path.join(root, parts[3]))
            return full if full.startswith(root + os.sep) and os.path.isfile(full) else None
    return None
