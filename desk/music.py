"""The tracks in ~/Music that a name fits (/api/music: the Music window, and TermNL's "play …")."""
import os
import re

import config
import tags

AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav")
IMAGES = (".jpg", ".jpeg", ".png", ".webp", ".gif")
plain = lambda t: " " + re.sub(r"[^a-z0-9]+", " ", t.lower()).strip() + " "


def music(query):
    """The tracks in ~/Music that a name fits: every word of it found in the artist, album or
    title (the folders and the file name). Nothing fits → the closest artist, album or title,
    for a typo. No name → everything. Tracks: { name, artist, album, path, cover }."""
    HOME = config.HOME
    root = os.path.join(HOME, "Music")
    tracks = []
    for folder, dirs, files in os.walk(root):
        dirs.sort()
        covers = sorted(f for f in files if f.lower().endswith(IMAGES))
        cover = next((f for f in covers if os.path.splitext(f)[0].lower() in ("cover", "folder", "front", "albumart", "album")),
                     covers[0] if covers else None)
        rel = os.path.relpath(folder, HOME)
        parts = os.path.relpath(folder, root).split(os.sep)
        for f in sorted(files):
            if f.lower().endswith(AUDIO):
                path = rel + "/" + f
                # no picture beside it (a track loose in Music, an album without cover.jpg): the one inside it, if any
                tracks.append({"name": re.sub(r"^\d+\s*[-.]\s*", "", os.path.splitext(f)[0]),
                               "artist": parts[0] if len(parts) > 1 else "", "album": parts[-1] if parts[0] != "." else "",
                               "path": path, "cover": rel + "/" + cover if cover else tags.inside_cover(path, os.path.join(folder, f))})
    words = plain(query).split()
    if not words:
        return tracks
    text = lambda t: plain(t["artist"] + " " + t["album"] + " " + t["name"])
    hits = [t for t in tracks if all(" " + w + " " in text(t) for w in words)]
    if not hits:
        import difflib
        names = {plain(t[k]).strip(): 1 for t in tracks for k in ("name", "album", "artist") if t[k]}
        close = difflib.get_close_matches(" ".join(words), list(names), n=1, cutoff=0.7)
        hits = [t for t in tracks if close and close[0] in (plain(t["name"]).strip(), plain(t["album"]).strip(), plain(t["artist"]).strip())]
    return hits
