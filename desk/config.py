"""What the desk's modules share: where the desk lives, desk.conf, and what the server was started with.
server.py sets the values once at start (its options); every module reads them here, as config.HOME and so on."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "web")  # the desk's page (from symbios/next/, the fold)
OLD = os.path.join(HERE, "app")  # the old page, at /old/, for the apps it still has alone (Ask, Slides, the Editor)

HOME = None            # the folder the skills work in (--home)
ALLOWED = set()        # the command groups that really run (--allow)
SHELL = []             # networks the Terminal's real shell opens for (--shell)
NEAR = []              # networks whose requests pass the lock as they are, from the desk's own page (--near)
CLAIM = []             # networks a phone may claim the desk over (--claim)
COMPANION = set()      # the only sites allowed to call the desk from a browser (--companion)
COMPANION_HOME = None  # the companion the claim QR code opens (desk.conf: the first companion)
LOCAL = None           # the board's own programs (desk-bluetooth): a pass in a file only the desk's user reads
TALK = None            # TermNL: loaded in this server, or its own service below the desk (talk.py)
SEALED_MOST = 100_001_000  # bytes of a sealed request: the inbox's 100 MB, its tag and a little more


def conf(path=os.path.join(HERE, "desk.conf")):
    """desk.conf: "name = value" lines, # for notes. What changes with where things live."""
    found = {}
    with open(path) as f:
        for line in f:
            name, _, value = line.partition("=")
            if value and not name.strip().startswith("#"):
                found[name.strip()] = value.strip()
    return found
