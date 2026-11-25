#!/bin/bash
# SymbiOS, layer 3: the shell. The desk, SymbiOS's face, on top of TermNL: its page and server read-only in
# /opt/symbios/desk, talking to TermNL on its socket; the kiosk on an HDMI screen (the browser pinned at the
# versions that work, VERSIONS.md); the phone's Bluetooth link; the models the desk's apps use (speech to text,
# search by meaning). Run on the board after install-base.sh and install-termnl.sh:
#     sudo ./install-desk.sh <desk folder>      (a copy of the desk repository, its fold branch; Mesh is part of it)
# Safe to run again: an update replaces the program, never the person's files or the desk's keys.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
SRC="$(cd "${1:?the desk folder}" && pwd)"
[ -f "$SRC/server.py" ] || { echo "no desk in $SRC"; exit 1; }
[ -z "${2:-}" ] || echo "   (a second folder is no longer needed: Mesh is part of the desk since 24 Nov; $2 is left aside)"
[ -S /run/symbios/termnl.sock ] || { echo "no TermNL below (/run/symbios/termnl.sock): run install-termnl.sh first"; exit 1; }
USER_NAME="${SUDO_USER:-$(logname)}"
[ "$USER_NAME" != root ] || { echo "run it as the board's user, with sudo (not as root itself)"; exit 1; }
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_ID="$(id -u "$USER_NAME")"
HERE="$(cd "$(dirname "$0")" && pwd)"
SH="$HERE/shell"
OPT=/opt/symbios/desk
fill() { sed -e "s#__USER__#$USER_NAME#g" -e "s#__UID__#$USER_ID#g" -e "s#__HOME__#$USER_HOME#g" "$1"; }
as_user() { sudo -u "$USER_NAME" bash -c "set -euo pipefail; $1"; }

echo "== packages"
# python3-cryptography: trust.py, the sealed link with the owner's phone; readability, html2text: article.py;
# poppler-utils: slides.py; ffmpeg: recordings for voice.py; python3-dbus-next: desk-bluetooth talks to BlueZ;
# python3-qrcode: the claim card's QR code (lock.py; without it the card shows the code alone); python3-usb: Mesh,
# for a radio with no serial port of its own (here the serial port is used first)
PKGS=(python3-cryptography python3-readability python3-html2text poppler-utils ffmpeg python3-dbus-next python3-qrcode python3-usb)
# the kiosk: the browser at the versions that work (VERSIONS.md), the Mali driver, a font, GStreamer for the
# Music and Video apps on the screen (bad + gl: video), wlr-randr for 720p
KIOSK=(cog=0.18.4-1+b1 cage=0.2.0-2 libwpewebkit-2.0-1=2.48.3-1 libwpe-1.0-1=1.16.2-1 libwpebackend-fdo-1.0-1=1.16.0-1 libwlroots-0.18=0.18.2-3)
PKGS+=("${KIOSK[@]}" libgl1-mesa-dri libgles2 fonts-dejavu-core gstreamer1.0-plugins-base gstreamer1.0-plugins-good
       gstreamer1.0-plugins-bad gstreamer1.0-gl wlr-randr)
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${PKGS[@]}" || {
  echo "   if Debian no longer has these versions: copy archive/debs-arm64 (VERSIONS.md) to the board and"
  echo "   apt install ./debs-arm64/*.deb, then run this again"; exit 1; }
# held: a newer WebKit broke the screen (15 Oct); updated by hand only, with a kiosk check (Gab, 31 Oct)
apt-mark hold "${KIOSK[@]%%=*}" >/dev/null
echo "   kiosk browser held: $(dpkg-query -W -f '${Package} ${Version}, ' "${KIOSK[@]%%=*}")"

echo "== the desk in $OPT, read-only"
rsync -a --delete --chown=root:root --chmod=go-w \
  --exclude .git --exclude home --exclude .trust --exclude '__pycache__' --exclude bench --exclude 'board/image' \
  --exclude '*.pdf' --exclude '*.pptx' --exclude 'voice memo' --exclude 'HANDOVER*' --exclude 'Pitch.txt' \
  "$SRC/" "$OPT/"
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

echo "== speech to text in ~/.models/transcribe: sherpa-onnx, Silero and Parakeet TDT 110M (voice.py)"
# as the desk's own install.sh does: each part unpacked aside and moved in only when complete
STT="$USER_HOME/.models/transcribe"; REL=https://github.com/k2-fsa/sherpa-onnx/releases/download
SHERPA=sherpa-onnx-v1.13.8-linux-aarch64-shared-cpu
PARAKEET=sherpa-onnx-nemo-parakeet_tdt_transducer_110m-en-36000-int8
as_user "mkdir -p '$STT'; rm -rf '$STT/.new'"
[ -d "$STT/lib" ] || as_user "mkdir '$STT/.new'; curl -fsSL '$REL/v1.13.8/$SHERPA.tar.bz2' \
  | tar xj -C '$STT/.new' --strip-components=1 '$SHERPA/bin/sherpa-onnx-vad-with-offline-asr' '$SHERPA/lib'
  mv '$STT/.new/bin' '$STT/.new/lib' '$STT/'; rmdir '$STT/.new'"
[ -f "$STT/silero_vad.onnx" ] || as_user "curl -fsSL -o '$STT/.new' '$REL/asr-models/silero_vad.onnx'; mv '$STT/.new' '$STT/silero_vad.onnx'"
[ -d "$STT/parakeet-tdt-110m" ] || as_user "mkdir '$STT/.new'; curl -fsSL '$REL/asr-models/$PARAKEET.tar.bz2' \
  | tar xj -C '$STT/.new' --strip-components=2 --wildcards '*.onnx' '*/tokens.txt'; mv '$STT/.new' '$STT/parakeet-tdt-110m'"

echo "== search by meaning in ~/.models/compare: MiniLM, with onnxruntime and numpy in ~/.models/shared/python"
# MiniLM from Hugging Face; onnxruntime and numpy from PyPI (Debian's crash on this board), checked against
# PyPI's sha256 and unpacked, as the board has no pip
CMP="$USER_HOME/.models/compare/all-minilm-l6-v2"; PY="$USER_HOME/.models/shared/python"
HF=https://huggingface.co/Xenova/all-MiniLM-L6-v2/resolve/main
as_user "mkdir -p '$USER_HOME/.models/compare' '$USER_HOME/.models/shared'; rm -rf '$CMP.new' '$PY.new'"
[ -f "$CMP/model_quantized.onnx" ] || as_user "mkdir '$CMP.new'; curl -fsSL -o '$CMP.new/tokenizer.json' '$HF/tokenizer.json'
  curl -fsSL -o '$CMP.new/model_quantized.onnx' '$HF/onnx/model_quantized.onnx'; mv '$CMP.new' '$CMP'"
wheel() {  # package, version, file: PyPI's file, its sha256 checked, unpacked into $PY.new
  local url sum
  read -r url sum < <(curl -fsSL "https://pypi.org/pypi/$1/$2/json" | python3 -c 'import json, sys
f = [u for u in json.load(sys.stdin)["urls"] if u["filename"] == sys.argv[1]][0]
print(f["url"], f["digests"]["sha256"])' "$3")
  as_user "curl -fsSL -o '$PY.new/$3' '$url'; echo '$sum  $PY.new/$3' | sha256sum -c --quiet
    python3 -m zipfile -e '$PY.new/$3' '$PY.new'; rm '$PY.new/$3'"
}
if [ ! -d "$PY/onnxruntime" ]; then
  as_user "mkdir '$PY.new'"
  wheel numpy 2.5.3 numpy-2.5.3-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl
  wheel onnxruntime 1.30.0 onnxruntime-1.30.0-cp313-cp313-manylinux_2_28_aarch64.whl
  as_user "mv '$PY.new' '$PY'"
fi

echo "== the secure link's keys, outside the home folder, for $USER_NAME only"
install -d -m 0700 -o "$USER_NAME" -g "$USER_NAME" /var/lib/desk-trust

echo "== the desk: desk.service, on port 80, TermNL below on its socket"
fill "$SH/desk.service" > /etc/systemd/system/desk.service
systemctl daemon-reload
systemctl enable desk.service
systemctl restart desk.service

echo "== Bluetooth: the board says where it is, so the phone finds it on any WiFi, and steers the screen"
echo uinput > /etc/modules-load.d/desk-uinput.conf
modprobe uinput || true
install -m 0644 "$OPT/board/99-desk-uinput.rules" /etc/udev/rules.d/
usermod -aG input,bluetooth "$USER_NAME"
udevadm control --reload && udevadm trigger --sysname-match=uinput || true
install -d -o "$USER_NAME" -g "$USER_NAME" "$USER_HOME/.config/systemd/user"
fill "$SH/desk-bluetooth.service" > "$USER_HOME/.config/systemd/user/desk-bluetooth.service"
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.config/systemd/user/desk-bluetooth.service"
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user daemon-reload
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user enable desk-bluetooth.service
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user restart desk-bluetooth.service \
  || echo "   Bluetooth did not start now; check: journalctl --user -u desk-bluetooth"

echo "== the kiosk on tty1, when an HDMI screen is plugged in"
fill "$SH/desk-kiosk.service" > /etc/systemd/system/desk-kiosk.service
install -m 0755 "$OPT/board/desk-hdmi-hotplug.sh" /usr/local/sbin/
install -m 0644 "$OPT/board/99-desk-hdmi.rules" /etc/udev/rules.d/
usermod -aG video,render,input "$USER_NAME"
udevadm control --reload-rules
systemctl daemon-reload
systemctl enable desk-kiosk.service
systemctl restart desk-kiosk.service || echo "   the kiosk did not start now (no screen plugged in?); it starts when one is"

echo "== TermNL asks the desk's documents (Ask) for what it doesn't know"
systemctl restart termnl.service
ok=0; for i in $(seq 1 30); do curl -fs -m 2 http://localhost/api/hello >/dev/null && { ok=1; break; }; sleep 1; done
[ $ok = 1 ] || { echo "the desk did not answer: journalctl -u desk"; exit 1; }
echo "== done: the desk on http://$(hostname -I | cut -d' ' -f1)/ (WiFi), http://10.55.0.1/ (cable), and on an HDMI screen"
