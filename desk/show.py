"""The slide on show, kept here so that every screen showing the deck (the board's own, a laptop on the cable)
and the phone (through desk-bluetooth) follow the same one. Changed by words, the same whoever sends them:
"open <deck>", "next", "prev", "go <n>", "black", "full", "end". black blanks the screen and keeps the place;
full puts the deck in its window and back on the whole screen. seq grows at each change, so a follower asks for
what came after the one it has."""
import os
import threading

import config

SHOW = {"seq": 0, "deck": None, "i": 0, "n": 0, "black": False, "full": False}
SHOWN = threading.Condition()


def steer_slides(words):
    """Apply one line of words to SHOW, and answer it (or raise ValueError for a line that makes no sense)."""
    import slides
    verb, _, rest = words.strip().partition(" ")
    if verb == "open":  # only a deck whose slides are made: one being made can't be shown yet
        import inbox as router
        if rest not in slides.shelf(os.path.join(config.HOME, "Slides")):
            raise ValueError("no deck called “%s” in ~/Slides" % rest)
        if not router.deck_ready(os.path.join(config.HOME, "Slides", rest)):
            raise ValueError("“%s” is being prepared; it can be shown once its slides are made" % rest)
        count = slides.prepare(os.path.join(config.HOME, "Slides", rest))["count"]
    with SHOWN:
        now = dict(SHOW)
        if verb == "open":
            now.update(deck=rest, i=1, n=count, black=False, full=True)
        elif verb == "end":
            now.update(deck=None, i=0, n=0, black=False, full=False)
        elif not now["deck"]:
            raise ValueError("no deck is open")
        elif verb in ("next", "prev"):
            now.update(i=max(1, min(now["n"], now["i"] + (1 if verb == "next" else -1))), black=False)
        elif verb == "go":
            if not rest.isdigit():
                raise ValueError("go needs a slide number")
            now.update(i=max(1, min(now["n"], int(rest))), black=False)
        elif verb == "black":
            now["black"] = not now["black"]
        elif verb == "full":
            now["full"] = not now["full"]
        else:
            raise ValueError("“%s” isn't a word the slides know" % verb)
        if now != SHOW:
            now["seq"] += 1
            SHOW.update(now)
            SHOWN.notify_all()
        return dict(SHOW)


def follow_slides(after, wait=25):
    """The slide on show once it is newer than seq after (at once if it already is), or as it is after wait seconds."""
    with SHOWN:
        SHOWN.wait_for(lambda: SHOW["seq"] != after, timeout=wait)
        return dict(SHOW)
