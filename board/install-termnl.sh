#!/bin/bash
# SymbiOS, layer 2: the foundation. TermNL as a service of its own, answering on a local socket only
# (/run/symbios/termnl.sock, which only the board's user may open), the program read-only in /opt, the
# person's own files in ~/.config/termnl, and the board's way to do what needs root (WiFi, power,
# restarting a service) as a short fixed list. Run on the board after install-base.sh:
#     sudo ./install-termnl.sh <TermNL folder>      (a copy of the TermNL repository, its symbios branch)
# Safe to run again: an update replaces the program, never the person's files.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
SRC="$(cd "${1:?the TermNL folder}" && pwd)"
[ -f "$SRC/termnl/server.py" ] || { echo "no TermNL in $SRC"; exit 1; }
USER_NAME="${SUDO_USER:-$(logname)}"
[ "$USER_NAME" != root ] || { echo "run it as the board's user, with sudo (not as root itself)"; exit 1; }
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_ID="$(id -u "$USER_NAME")"
HERE="$(cd "$(dirname "$0")" && pwd)"
F="$HERE/foundation"
OPT=/opt/symbios/termnl
NP=/opt/symbios/termnl-python   # numpy, for TermNL's learning only (below)
DATA="$USER_HOME/.config/termnl"

echo "== TermNL in $OPT, read-only"
# the program only: its tests, logs and personal settings stay out (the settings come from its template)
install -d -m 0755 /opt/symbios
rsync -a --delete --chown=root:root --chmod=go-w \
  --exclude .git --exclude logs --exclude tests --exclude briefs --exclude '__pycache__' --exclude 'model.previous.json' \
  "$SRC/" "$OPT/"
python3 -m compileall -q "$OPT/termnl"
# which TermNL this is: its git commit, or the COMMIT file the copy from the laptop carries (README.md)
(cd "$SRC" && git log -1 --format='%h %s' 2>/dev/null || cat "$SRC/COMMIT" 2>/dev/null || echo "unknown") | cut -c1-100 > "$OPT/COMMIT"
echo "   TermNL $(cat "$OPT/COMMIT")"

echo "== numpy for TermNL's learning, in $NP (read-only)"
# Recognising needs only the standard library; training ("learn what I taught you") needs numpy. Not Debian's (the
# desk's note: "Debian's crash on this board"): PyPI's file, its sha256 checked, unpacked, as the board has no pip.
# TermNL's own, below the desk: the desk's copy in ~/.models/shared/python comes a layer later and is the desk's.
# (Until 26 Nov no installer gave TermNL numpy: "learn" said it was starting and stopped at "No module named numpy".)
NP_VER=2.5.3; NP_WHL=numpy-$NP_VER-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
if [ ! -d "$NP/numpy-$NP_VER.dist-info" ]; then
  rm -rf "$NP.new"; install -d -m 0755 "$NP.new"
  read -r url sum < <(curl -fsSL "https://pypi.org/pypi/numpy/$NP_VER/json" | python3 -c 'import json, sys
f = [u for u in json.load(sys.stdin)["urls"] if u["filename"] == sys.argv[1]][0]
print(f["url"], f["digests"]["sha256"])' "$NP_WHL")
  curl -fsSL -o "$NP.new/$NP_WHL" "$url"
  echo "$sum  $NP.new/$NP_WHL" | sha256sum -c --quiet
  python3 -m zipfile -e "$NP.new/$NP_WHL" "$NP.new"; rm "$NP.new/$NP_WHL"
  chown -R root:root "$NP.new"; chmod -R go-w "$NP.new"
  rm -rf "$NP"; mv "$NP.new" "$NP"
fi
sudo -u "$USER_NAME" env PYTHONPATH="$NP" python3 -c 'import numpy; print("   numpy", numpy.__version__)'

echo "== the person's own files in $DATA"
sudo -u "$USER_NAME" mkdir -p "$DATA"
if [ ! -f "$DATA/settings.md" ]; then
  # TermNL's template, made for a board: home is the whole home folder; only switching the WiFi off and on is
  # pretended (on a board with no screen it cuts the way in); no name yet ("call me …" sets it)
  sed -e 's/^home: .*/home: ~/' -e 's/^simulate: .*/simulate: turn on wifi, turn off wifi/' "$OPT/settings.md" \
    | sudo -u "$USER_NAME" tee "$DATA/settings.md" >/dev/null
fi
# how this board scans and joins WiFi, powers off and restarts: lent to TermNL in place of its skills' own;
# the board's, not the person's: written again by every run of this installer
install -m 0644 -o "$USER_NAME" -g "$USER_NAME" "$F/commands.json" "$DATA/commands.json"

echo "== what TermNL may do as root: WiFi, power, restarting a service (nothing else)"
install -m 0755 "$F/symbios-wifi" /usr/local/sbin/symbios-wifi
install -D -m 0755 "$F/symbios-wifi-said" /usr/local/lib/symbios/symbios-wifi-said
# the networks the card was written with, under the helper's own name
[ -f /etc/netplan/60-desk-wifi.yaml ] && [ ! -f /etc/netplan/60-symbios-wifi.yaml ] && mv /etc/netplan/60-desk-wifi.yaml /etc/netplan/60-symbios-wifi.yaml
sed "s#__USER__#$USER_NAME#g" "$F/sudoers-termnl" > /etc/sudoers.d/symbios-termnl
chmod 440 /etc/sudoers.d/symbios-termnl
visudo -cf /etc/sudoers.d/symbios-termnl >/dev/null

echo "== the service: termnl.service, on /run/symbios/termnl.sock"
# the unit and the program must be the same step: every option the unit passes is one this TermNL knows
# (31 Oct: a unit with --docs over a TermNL without it restarted in a loop)
HELP=$(cd "$OPT" && python3 -m termnl.server --help)
for flag in $(grep '^ExecStart=' "$F/termnl.service" | grep -o -- '--[a-z-]*'); do
  grep -q -- "$flag" <<<"$HELP" || { echo "this TermNL ($(cat "$OPT/COMMIT")) has no $flag, which termnl.service passes: copy the TermNL that goes with these files"; exit 1; }
done
sed -e "s#__USER__#$USER_NAME#g" -e "s#__UID__#$USER_ID#g" -e "s#__HOME__#$USER_HOME#g" "$F/termnl.service" > /etc/systemd/system/termnl.service
systemctl daemon-reload
systemctl enable termnl.service
systemctl restart termnl.service

echo "== the termnl command: talk to the board from its terminal or over SSH"
install -m 0755 "$F/termnl" /usr/local/bin/termnl
# a real answer, not only the socket file: on a run again the old one is there until the new TermNL replaces it
ok=0; for i in $(seq 1 30); do sudo -u "$USER_NAME" termnl hello 2>/dev/null && { ok=1; break; }; sleep 1; done
[ $ok = 1 ] || { echo "TermNL did not answer: journalctl -u termnl"; exit 1; }
echo "== done: foundation of $(hostname). Try: termnl how much space is left?"
