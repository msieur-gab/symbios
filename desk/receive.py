"""A file arriving in ~/Inbox (/api/inbox): dropped on the desk or sent by the phone, kept once, then placed by the
rulebook (inbox.py, ~/Inbox/rules.md)."""
import hashlib
import os
import threading
import time
from urllib.parse import parse_qs, urlparse

import config

RECEIVING = threading.Lock()  # the inbox's list of what arrived, read and written by one upload at a time


class InboxRoutes:
    """The server's /api/inbox (mixed into its handler)."""

    def inbox(self):
        """A file dropped on the desk or sent by the phone → ~/Inbox, as it is: the body is the file, ?name=
        its name, ?modified= its time (ms) so a recording keeps when it was made, ?source= what the sender
        says it is (recorder, scan, camera, share, desk). From there it goes where the rulebook says
        (inbox.py, ~/Inbox/rules.md); the answer says where ("went"). Locked (gate): over the WiFi only the owner's
        phone drops one, sealed; the board's own screen and the cable as they are."""
        import inbox as router
        HOME = config.HOME
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        source = q.get("source", "any").strip().lower()
        source = source if source in router.SOURCES else "any"
        size = int(self.headers.get("Content-Length", 0))
        name = os.path.basename(q.get("name", "")).strip()
        if not name or name.startswith("."):
            return self.fail(400, "expected ?name=")
        if size > 100_000_000:
            return self.fail(413, "too large for the inbox (100 MB at most)")
        inbox = os.path.join(HOME, "Inbox")
        os.makedirs(inbox, exist_ok=True)
        stem, ext = os.path.splitext(name)
        final, n = os.path.join(inbox, name), 1
        while os.path.exists(final):
            n += 1
            final = os.path.join(inbox, "%s (%d)%s" % (stem, n, ext))
        part = os.path.join(inbox, ".arriving-" + os.path.basename(final))  # hidden while it arrives
        digest = hashlib.sha256()
        with open(part, "wb") as f:
            left = size
            while left > 0:
                piece = self.rfile.read(min(65536, left))
                if not piece:
                    break
                f.write(piece)
                digest.update(piece)
                left -= len(piece)
        if left:
            os.remove(part)
            return self.fail(400, "the file arrived cut short")
        # The same bytes sent again (the phone retrying after a cut, a second tap) are kept once: every file
        # that arrived is listed in Inbox/.received, as its hash, the day it came and the name it got.
        ledger, digest = os.path.join(inbox, ".received"), digest.hexdigest()
        with RECEIVING:
            first = None
            if os.path.isfile(ledger):
                for line in open(ledger, encoding="utf-8"):
                    seen = line.rstrip("\n").split("\t")
                    if seen[0] == digest:
                        first = seen
                        break
            if first:
                os.remove(part)
                return self.send({"path": first[2], "duplicate": True, "first": first[1]})
            with open(ledger, "a", encoding="utf-8") as f:
                f.write("%s\t%s\t%s\t%s\n" % (digest, time.strftime("%Y-%m-%d %H:%M"), os.path.relpath(final, HOME), source))
        try:
            t = int(q["modified"]) / 1000
            os.utime(part, (t, t))
        except (KeyError, ValueError):
            pass
        os.replace(part, final)
        went = router.place(HOME, final, source)  # the rulebook, ~/Inbox/rules.md
        if went and went.startswith("Articles/") and went.endswith(".md"):  # an article sent as a file: in Activity now
            import voice
            voice.announce(os.path.join(HOME, went), HOME)
        self.send({"path": os.path.relpath(final, HOME), "went": went, "voice": went is not None and went.startswith("Memos/")})
