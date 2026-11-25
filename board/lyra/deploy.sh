#!/bin/bash
# From the laptop, over SSH as root by the laptop's key: SymbiOS's three layers onto a Luckfox Lyra Zero W, as
# board/README.md does on the Orange Pi. Each tree is a commit, never a working copy: what is on the board is what git
# has. Only what changed is written on the board (rsync by content), which spares its SD card (Gab, 24 Nov: "we cannot
# all the time push the full build again, which is destroying the SD card").
#     board/lyra/deploy.sh [base] [termnl] [desk]        (all three by default, in that order)
# Where: LYRA (default lyra.lan, else 10.55.0.1, the cable; its WiFi address works as well): the board is known by
# its own SSH host key (HostKeyAlias lyra), read over the cable the first time, so another machine at that address
# can't pass for it.
# Which commits: DESK_REF (default fold), TERMNL_REF (symbios), from ~/dev/desk and ~/dev/TermNL (DEV to change ~/dev);
# this folder's board/ as this repository's HEAD has it. Mesh is part of the desk since 24 Nov.
# On a fresh card: WPA=<wpa_supplicant file> for the WiFi to join, MODELS=<tar of ~/.models> to skip downloading them.
# A fresh card has no key for root yet: the first run puts the laptop's there over adb, the card's only way in, and
# the base layer then takes adb off the cable for good (Gab, 24 Nov: "Root by the laptop's key"; symbios SECURITY.md,
# the review of 24 Nov, B1 to B3).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
DEV=${DEV:-$HOME/dev}
DESK_REF=${DESK_REF:-fold}; TERMNL_REF=${TERMNL_REF:-symbios}
# the router's name for it comes and goes (lyra.lan stopped resolving on 24 Nov): without LYRA, that name if it
# resolves, else the cable's address
LYRA=${LYRA:-$(getent hosts lyra.lan >/dev/null && echo lyra.lan || echo 10.55.0.1)}
U=lyra; H=/home/$U
SRC=/var/lib/symbios-src  # root's alone (0700): a layer is never run from a folder anyone else can change (B2)
KEY="$HOME/.ssh/id_ed25519.pub"
SSH_OPTS="-o BatchMode=yes -o ConnectTimeout=10 -o HostKeyAlias=lyra -o StrictHostKeyChecking=yes"
SSH=(ssh $SSH_OPTS "root@$LYRA")
LAYERS=("$@"); [ ${#LAYERS[@]} -gt 0 ] || LAYERS=(base termnl desk)
on() { "${SSH[@]}" "umask 077; $*"; }

# ---- a fresh card: root's key and the board's host key, over adb (root on the cable), once
if ! "${SSH[@]}" true 2>/dev/null; then
  A="adb ${ADB_SERIAL:+-s $ADB_SERIAL}"
  $A get-state >/dev/null 2>&1 || { echo "root@$LYRA doesn't take the laptop's key, and no board is on adb to give it"; exit 1; }
  echo "== a fresh card: the laptop's key for root and for $U, the board's host key read over the cable"
  K=$(cat "$KEY")
  for home in /root "$H"; do
    who=$([ "$home" = /root ] && echo root || echo $U)
    $A shell "install -d -m 700 -o $who -g $who $home/.ssh && touch $home/.ssh/authorized_keys && (grep -qF '$K' $home/.ssh/authorized_keys || echo '$K' >> $home/.ssh/authorized_keys); chown $who:$who $home/.ssh/authorized_keys; chmod 600 $home/.ssh/authorized_keys"
  done
  ssh-keygen -R lyra >/dev/null 2>&1 || true
  $A shell "cat /etc/ssh/ssh_host_ed25519_key.pub" | tr -d '\r' | awk '{print "lyra", $1, $2}' >> "$HOME/.ssh/known_hosts"
  "${SSH[@]}" true || { echo "root@$LYRA still refuses the key over SSH"; exit 1; }
fi

push() {  # repository, ref, path inside it ("" for all), name: that commit's tree to $SRC/<name>, only what changed
  local t; t=$(mktemp -d)
  chmod 755 "$t"  # mktemp's 0700 would travel with the tree into /opt: TermNL couldn't enter its folder (24 Nov)
  git -C "$1" archive --format=tar "$2" ${3:+"$3"} | tar -x -C "$t"
  git -C "$1" log -1 --format='%h %s' "$2" | cut -c1-100 > "$t/COMMIT"
  # $SRC itself is root's alone, so nobody else reaches what is inside; the trees keep git's modes, as the layers copy
  # them into /opt as they are (a tree readable by root alone would leave the desk unable to read its own code)
  on "install -d -m 700 $SRC && install -d -m 755 $SRC/$4"
  rsync -rlpc --chmod=go-w --delete -e "ssh $SSH_OPTS" "$t/" "root@$LYRA:$SRC/$4/" >/dev/null
  rm -rf "$t"
  echo "   $4: $(git -C "$1" log -1 --format='%h' "$2") ($2)"
}

echo "== the code, as committed, to $SRC (only what changed)"
push "$REPO" HEAD board board
push "$DEV/TermNL" "$TERMNL_REF" "" termnl
push "$DEV/desk" "$DESK_REF" "" desk

echo "== the laptop's SSH key for root and for $U"
K=$(cat "$KEY")
for home in /root "$H"; do
  who=$([ "$home" = /root ] && echo root || echo $U)
  on "install -d -m 700 -o $who -g $who $home/.ssh && touch $home/.ssh/authorized_keys && (grep -qF '$K' $home/.ssh/authorized_keys || echo '$K' >> $home/.ssh/authorized_keys); chown $who:$who $home/.ssh/authorized_keys; chmod 600 $home/.ssh/authorized_keys"
done

if [ -n "${MODELS:-}" ] && [ "$(on "[ -d $H/.models/transcribe/lib ] && echo yes" || true)" != yes ]; then
  echo "== the models from $MODELS (a tar of ~/.models, saved from a board), instead of downloading them on the board"
  "${SSH[@]}" "tar -C $H -xf - && chown -R $U:$U $H/.models" < "$MODELS"
fi
WPA_ON_BOARD=
if [ -n "${WPA:-}" ]; then  # the WiFi to join (a wpa_supplicant file); given to the base layer, then removed
  "${SSH[@]}" "umask 077; cat > /root/wpa.conf" < "$WPA"; WPA_ON_BOARD=/root/wpa.conf
fi

B=$SRC/board/board/lyra
run() {  # a layer on the board, run there by systemd (a session that ends would stop it half-way: 23 Nov, the
  # language step took minutes), its log followed from here; its exit code is written at the end of the log
  local log=/var/log/symbios-install.log n=0 seen=0
  on "systemctl reset-failed symbios-install 2>/dev/null; : > $log; chmod 600 $log; systemd-run --quiet --collect --unit=symbios-install \
    -p StandardOutput=append:$log -p StandardError=append:$log /bin/bash -c 'bash $*; echo layer-exit=\$?'"
  while :; do
    sleep 5
    n=$(on "wc -l < $log" | tr -d '\r\n ')
    [ "$n" -gt "$seen" ] && { on "tail -n +$((seen + 1)) $log | head -n $((n - seen))"; seen=$n; }
    [ "$(on "systemctl is-active symbios-install" || true)" = active ] || break
  done
  on "tail -n +$((seen + 1)) $log"
  on "cat $log" | grep -q '^layer-exit=0' || { echo "== stopped: $(basename "$1") failed (the board's $log)"; exit 1; }
}
for l in "${LAYERS[@]}"; do
  case $l in
    base) run "$B/install-base.sh" $WPA_ON_BOARD ;;
    termnl) run "$B/install-termnl.sh" "$SRC/termnl" ;;
    desk) run "$B/install-desk.sh" "$SRC/desk" ;;
    *) echo "no layer $l"; exit 1 ;;
  esac
done
[ -n "$WPA_ON_BOARD" ] && on "rm -f $WPA_ON_BOARD"

# the base layer took adb off the cable: it holds from the next start; the board comes back over SSH
if [ "$(on "[ -e /run/symbios-restart-needed ] && echo yes" || true)" = yes ]; then
  echo "== restarting the board, for the cable without adb"
  on "systemctl reboot" || true
  sleep 20
  for i in $(seq 1 40); do "${SSH[@]}" true 2>/dev/null && break; sleep 5; done
  "${SSH[@]}" true || { echo "== the board didn't come back over SSH within 4 minutes"; exit 1; }
  echo "   back: $(on "uptime -p")"
fi
echo "== done"
