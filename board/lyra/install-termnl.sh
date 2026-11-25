#!/bin/bash
# SymbiOS, layer 2 on a Luckfox Lyra Zero W: the foundation, as ../install-termnl.sh makes it on the Orange Pi.
# The same: TermNL in /opt/symbios/termnl, read-only, its own service (../foundation/termnl.service) answering only
# on /run/symbios/termnl.sock, the person's files in ~/.config/termnl, a fixed list of what it may do as root.
# The same WiFi helper too (symbios-wifi), which keeps networks through wpa_supplicant here, as this image has no netplan.
# Run on the board as root, after install-base.sh:
#     install-termnl.sh <TermNL folder>      (a copy of the TermNL repository, its symbios branch)
# Safe to run again: an update replaces the program, never the person's files.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
SRC="$(cd "${1:?the TermNL folder}" && pwd)"
[ -f "$SRC/termnl/server.py" ] || { echo "no TermNL in $SRC"; exit 1; }
USER_NAME="${SUDO_USER:-lyra}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_ID="$(id -u "$USER_NAME")"
HERE="$(cd "$(dirname "$0")" && pwd)"
F="$HERE/../foundation"
OPT=/opt/symbios/termnl
DATA="$USER_HOME/.config/termnl"

echo "== TermNL in $OPT, read-only"
install -d -m 0755 /opt/symbios
rsync -a --delete --chown=root:root --chmod=go-w \
  --exclude .git --exclude logs --exclude tests --exclude briefs --exclude '__pycache__' --exclude 'model.previous.json' \
  "$SRC/" "$OPT/"
python3 -m compileall -q "$OPT/termnl"
(cd "$SRC" && git log -1 --format='%h %s' 2>/dev/null || cat "$SRC/COMMIT" 2>/dev/null || echo "unknown") | cut -c1-100 > "$OPT/COMMIT"
echo "   TermNL $(cat "$OPT/COMMIT")"

echo "== the person's own files in $DATA"
sudo -u "$USER_NAME" mkdir -p "$DATA"
if [ ! -f "$DATA/settings.md" ]; then
  sed -e 's/^home: .*/home: ~/' -e 's/^simulate: .*/simulate: turn on wifi, turn off wifi/' "$OPT/settings.md" \
    | sudo -u "$USER_NAME" tee "$DATA/settings.md" >/dev/null
fi
install -m 0644 -o "$USER_NAME" -g "$USER_NAME" "$F/commands.json" "$DATA/commands.json"

echo "== what TermNL may do as root: WiFi, power, restarting a service (nothing else)"
install -m 0755 "$F/symbios-wifi" /usr/local/sbin/symbios-wifi
install -D -m 0755 "$F/symbios-wifi-said" /usr/local/lib/symbios/symbios-wifi-said
sed "s#__USER__#$USER_NAME#g" "$F/sudoers-termnl" > /etc/sudoers.d/symbios-termnl
chmod 440 /etc/sudoers.d/symbios-termnl
visudo -cf /etc/sudoers.d/symbios-termnl >/dev/null

echo "== the service: termnl.service, on /run/symbios/termnl.sock"
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
ok=0; for i in $(seq 1 60); do sudo -u "$USER_NAME" termnl hello 2>/dev/null && { ok=1; break; }; sleep 1; done
[ $ok = 1 ] || { echo "TermNL did not answer: journalctl -u termnl"; exit 1; }
echo "== done: foundation of $(hostname). Try: termnl how much space is left?"
