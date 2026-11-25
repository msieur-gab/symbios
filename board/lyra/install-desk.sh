#!/bin/bash
# SymbiOS, layer 3 on a Luckfox Lyra Zero W: the shell, as ../install-desk.sh makes it on the Orange Pi. The same:
# the desk read-only in /opt/symbios/desk, on top of TermNL on its socket (../shell/desk.service: --termnl, the
# person's whole home, --allow all, the real shell for the board and the cable), the secure link's keys in
# /var/lib/desk-trust. What differs is what the board has:
# - no HDMI: no kiosk; the e-ink card instead (the address, the QR code to join)
# - Bluetooth: none. On this board WiFi and Bluetooth can't run together: a GATT server with the WiFi up resets the
#   chip's USB within seconds (seen 24 Nov; Luckfox's engineer, forums.luckfox.com t=2670). desk-bluetooth for the
#   Lyra is parked on branch lyra-bluetooth, for a Bluetooth-when-the-WiFi-is-off later
# - its own desk.conf (the desk's board/lyra/desk.conf: the companions, Mesh, the heavy-job limits)
# - its models for 32-bit ARM (the desk's board/lyra/fetch-models.sh)
# - Mesh, the desk's own since 24 Nov (its mesh/ folder), the radio on USB through pyusb
# On a board set up before SymbiOS (the desk in ~/dev/desk, by the desk's board/lyra/install.sh), it carries over
# what was there, untouched: the claim (its keys and owners) and the person's files, copied into their home.
# Run on the board as root, after install-base.sh and install-termnl.sh:
#     install-desk.sh <desk folder>
# Safe to run again: an update replaces the program, never the person's files or the desk's keys.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
SRC="$(cd "${1:?the desk folder}" && pwd)"
[ -f "$SRC/server.py" ] || { echo "no desk in $SRC"; exit 1; }
[ -S /run/symbios/termnl.sock ] || { echo "no TermNL below (/run/symbios/termnl.sock): run install-termnl.sh first"; exit 1; }
USER_NAME="${SUDO_USER:-lyra}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_ID="$(id -u "$USER_NAME")"
HERE="$(cd "$(dirname "$0")" && pwd)"
SH="$HERE/../shell"
OPT=/opt/symbios/desk
OLD="$USER_HOME/dev/desk"   # the desk before SymbiOS, on this board
fill() { sed -e "s#__USER__#$USER_NAME#g" -e "s#__UID__#$USER_ID#g" -e "s#__HOME__#$USER_HOME#g" "$1"; }

echo "== packages"
# python3-cryptography: trust.py; readability, html2text: article.py; poppler-utils: slides.py; ffmpeg: voice.py;
# numpy: embed.py; usb: Mesh; pil, spidev, libgpiod, qrcode: the e-ink card and its QR code
apt-get -o DPkg::Lock::Timeout=900 update -qq
DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y -q --no-install-recommends \
  python3-cryptography python3-readability python3-html2text poppler-utils ffmpeg python3-numpy \
  python3-usb python3-pil python3-spidev python3-libgpiod python3-qrcode

echo "== the desk in $OPT, read-only, with this board's desk.conf"
rsync -a --delete --chown=root:root --chmod=go-w \
  --exclude .git --exclude home --exclude .trust --exclude '__pycache__' --exclude bench --exclude 'board/image' \
  --exclude '*.pdf' --exclude '*.pptx' --exclude 'voice memo' --exclude 'HANDOVER*' --exclude 'Pitch.txt' \
  "$SRC/" "$OPT/"
install -m 0644 "$SRC/board/lyra/desk.conf" "$OPT/desk.conf"
# The companion, the phone's page: the address of the person's own copy (README, "The companion"), given once as
#     COMPANION="https://<its address>" on this command's line; kept in /etc/symbios/companion for the next installs.
# Without it, desk.conf's own line stays.
if [ -n "${COMPANION:-}" ]; then
  [[ "$COMPANION" =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?(\ https://[A-Za-z0-9.-]+(:[0-9]+)?)*$ ]] \
    || { echo "COMPANION: one or more https:// addresses, with no path (https://my-companion.example.org)"; exit 1; }
  install -d -m 0755 /etc/symbios && echo "$COMPANION" > /etc/symbios/companion
fi
[ -s /etc/symbios/companion ] && sed -i "s#^companion = .*#companion = $(cat /etc/symbios/companion)#" "$OPT/desk.conf"
echo "   companion: $(sed -n 's/^companion = //p' "$OPT/desk.conf")"
grep -q '^companion = none' "$OPT/desk.conf" \
  && echo "   no companion yet: run this again with COMPANION=\"https://<your companion's address>\" (README)"
python3 -m compileall -q "$OPT"
(cd "$SRC" && git log -1 --format='%h %s' 2>/dev/null || cat "$SRC/COMMIT" 2>/dev/null || echo "unknown") | cut -c1-100 > "$OPT/COMMIT"
echo "   desk $(cat "$OPT/COMMIT")"

echo "== Mesh, the desk's own (mesh/): the radio reachable without root; the separate copy of before 24 Nov removed"
rm -rf /opt/symbios/desk-meshtastic
rm -f "$(python3 -c 'import site; print(site.getsitepackages()[0])')/desk-meshtastic.pth"
install -m 644 "$OPT/board/99-desk-meshtastic.rules" /etc/udev/rules.d/
getent group plugdev >/dev/null || groupadd plugdev
usermod -aG plugdev,dialout "$USER_NAME"   # plugdev: a radio over USB; dialout: one with a serial port
udevadm control --reload; udevadm trigger

echo "== the models: speech to text and search by meaning, for 32-bit ARM, in ~/.models"
STT="$USER_HOME/.models/transcribe"; PY="$USER_HOME/.models/shared/python"
if [ -d "$STT/lib" ] && [ -d "$STT/parakeet-tdt-110m" ] && [ -f "$USER_HOME/.models/compare/all-minilm-l6-v2/model_quantized.onnx" ]; then
  echo "   already there"
else
  sudo -u "$USER_NAME" bash "$OPT/board/lyra/fetch-models.sh"
fi
if [ ! -d "$PY/onnxruntime" ]; then
  sudo -u "$USER_NAME" mkdir -p "$PY"
  sudo -u "$USER_NAME" cp -r "$OPT/board/lyra/onnxruntime" "$PY/onnxruntime"
fi

echo "== the desk stops while what it had is carried over"
systemctl stop desk.service 2>/dev/null || true
[ -f /etc/systemd/system/desk.service ] && ! grep -q termnl.sock /etc/systemd/system/desk.service \
  && cp -n /etc/systemd/system/desk.service /etc/systemd/system/desk.service.before-symbios

echo "== the secure link's keys, outside the home folder, for $USER_NAME only"
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" /var/lib/desk-trust
if [ -d "$OLD/.trust" ] && [ ! -e /var/lib/desk-trust/board.pem ]; then
  cp -a "$OLD/.trust/." /var/lib/desk-trust/
  echo "   carried over from $OLD/.trust: $(ls /var/lib/desk-trust | tr '\n' ' ')"
fi

echo "== the person's files in $USER_HOME"
# copied, not moved: the old folder stays as it was, to go back to; a file already in the home is never replaced
if [ -d "$OLD/home" ] && [ ! -e "$USER_HOME/.desk/carried-over" ]; then
  for e in "$OLD/home"/* "$OLD/home"/.[!.]*; do
    [ -e "$e" ] || continue
    n=$(basename "$e"); [ "$n" = .bash_history ] && continue
    cp -a -n "$e" "$USER_HOME/" 2>/dev/null || cp -a -n "$e/." "$USER_HOME/$n/"
  done
  chown -R "$USER_NAME:$USER_NAME" "$USER_HOME"/{Articles,Documents,Downloads,Inbox,Memos,Mesh,Music,Notes,Pictures,Videos,Local,.desk} 2>/dev/null || true
  sudo -u "$USER_NAME" mkdir -p "$USER_HOME/.desk"
  sudo -u "$USER_NAME" sh -c "echo '$OLD/home, $(date -Is)' > '$USER_HOME/.desk/carried-over'"
  echo "   from $OLD/home ($(du -sh "$OLD/home" | cut -f1))"
fi
# what was the desk before SymbiOS and its trials (the old desk, its backup, next/ and its test home) is not the
# person's: kept whole in a hidden folder, which the desk's index and Files leave out, to go back to or delete
for e in dev next next-home next.log; do
  [ -e "$USER_HOME/$e" ] || continue
  sudo -u "$USER_NAME" mkdir -p "$USER_HOME/.before-symbios"
  mv "$USER_HOME/$e" "$USER_HOME/.before-symbios/"
  echo "   $e kept in $USER_HOME/.before-symbios/"
done

echo "== the desk: desk.service, on port 80, TermNL below on its socket"
fill "$SH/desk.service" > /etc/systemd/system/desk.service

# The e-ink card only where its driver came with the desk: the public SymbiOS doesn't carry it (Gab, 25 Nov: "I will
# not support the e-ink driver"); without it, a screen on the cable shows the QR code to claim the board.
EINK=0; [ -f "$OPT/board/eink/desk-eink.py" ] && EINK=1
if [ $EINK = 1 ]; then
  echo "== the e-ink card (as root, for SPI and GPIO)"
  sed "s#^ExecStart=.*#ExecStart=/usr/bin/python3 $OPT/board/eink/desk-eink.py --port 80#" "$OPT/board/eink/desk-eink.service" \
    > /etc/systemd/system/desk-eink.service
fi

systemctl daemon-reload
systemctl enable desk.service
systemctl restart desk.service
[ $EINK = 1 ] && { systemctl enable desk-eink.service; systemctl restart desk-eink.service; }

echo "== TermNL asks the desk's documents (Ask) for what it doesn't know"
systemctl restart termnl.service
ok=0; for i in $(seq 1 60); do curl -fs -m 2 http://localhost/api/hello >/dev/null && { ok=1; break; }; sleep 1; done
[ $ok = 1 ] || { echo "the desk did not answer: journalctl -u desk"; exit 1; }
echo "== done: the desk on http://$(hostname -I | cut -d' ' -f1)/ (WiFi) and http://10.55.0.1/ (cable)"
