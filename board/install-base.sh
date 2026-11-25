#!/bin/bash
# SymbiOS, layer 1: the base. Turns a fresh Armbian board (after its first login) into a closed, named,
# updatable Linux computer, with the USB cable link, sound and the usual folders. Nothing of TermNL or
# the desk yet. Run on the board, from this folder:
#     sudo ./install-base.sh
# Safe to run again after a change.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
USER_NAME="${SUDO_USER:-$(logname)}"
[ "$USER_NAME" != root ] || { echo "run it as the board's user, with sudo (not as root itself)"; exit 1; }
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
USER_ID="$(id -u "$USER_NAME")"
HERE="$(cd "$(dirname "$0")" && pwd)"
B="$HERE/base"
NAME=symbios   # answers at http://symbios.local over the USB cable (the board's WiFi hears no .local names)

echo "== $USER_NAME without the disk and docker groups Armbian's first login gives"
# disk: raw read and write on the SD card, so whoever gets past the lock as the user becomes root (desk SECURITY.md 3.13;
# Gab, 2026-10-31: "fix 4 yes"); docker: not installed, and the same as root if it ever were
for g in disk docker; do id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx "$g" && gpasswd -d "$USER_NAME" "$g" >/dev/null; done

echo "== the user's SSH key is in place before passwords are switched off"
[ -s "$USER_HOME/.ssh/authorized_keys" ] || { echo "no key in $USER_HOME/.ssh/authorized_keys: SSH would lock $USER_NAME out"; exit 1; }

echo "== packages"
# avahi: the .local name; dnsmasq-base: DHCP on the USB cable; iw, wireless-tools: the WiFi as TermNL reads it;
# nftables: the firewall; unattended-upgrades: Debian's security fixes; PipeWire and pactl: sound, as on the desk;
# git, rsync: the layers above arrive this way; curl, bzip2: downloads of models later
PKGS=(python3 avahi-daemon dnsmasq-base iw wireless-tools nftables unattended-upgrades
      pipewire pipewire-pulse wireplumber pulseaudio-utils git rsync curl bzip2)
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${PKGS[@]}"

echo "== Armbian's own packages held: they change only on purpose, on a second card first"
# every installed package that Armbian's repositories offer: the kernel, device tree, u-boot, firmware,
# armbian-bsp-cli, base-files, armbian-config, Armbian's bluez build…
HOLD=$(cat /var/lib/apt/lists/*armbian*_Packages 2>/dev/null | sed -n 's/^Package: //p' | sort -u \
       | comm -12 - <(dpkg-query -W -f '${db:Status-Abbrev} ${Package}\n' | awk '$1 ~ /^.i/ {print $2}' | sort -u))
[ -n "$HOLD" ] && apt-mark hold $HOLD >/dev/null
echo "   held: $(echo $HOLD | wc -w) packages"

echo "== language: British English (Gab, 2026-10-31), whatever the first login chose"
# a decimal point, as TermNL reads command output; Armbian's first login also writes its choice into ~/.bashrc
sed -i -E 's/^# *(en_GB\.UTF-8 UTF-8)/\1/' /etc/locale.gen
locale-gen >/dev/null
printf 'LANG=en_GB.UTF-8\nLANGUAGE=en_GB:en\n' | tee /etc/locale.conf > /etc/default/locale
[ -f "$USER_HOME/.bashrc" ] && sed -i -E 's/^(export (LC_ALL|LANG|LANGUAGE)=).*/\1en_GB.UTF-8/' "$USER_HOME/.bashrc"

echo "== updates: Debian's security fixes only, no reboot by itself"
install -m 0644 "$B/52symbios-updates" /etc/apt/apt.conf.d/52symbios-updates
install -D -m 0644 "$B/wait-online-wlan0.conf" /etc/systemd/system/systemd-networkd-wait-online.service.d/symbios-wlan0.conf

echo "== SSH: by key only"
install -m 0644 "$B/00-symbios-ssh.conf" /etc/ssh/sshd_config.d/00-symbios-ssh.conf
sshd -t
systemctl reload ssh

echo "== name: $NAME.local"
hostnamectl set-hostname "$NAME"
sed -i -E "s/^127\.0\.1\.1.*/127.0.1.1\t$NAME/" /etc/hosts
sed -i -E "s/^#?host-name=.*/host-name=$NAME/" /etc/avahi/avahi-daemon.conf
systemctl restart avahi-daemon

echo "== USB cable: the board at http://$NAME.local or http://10.55.0.1 when plugged into a computer"
install -m 0755 "$B/symbios-usb-gadget.sh" /usr/local/sbin/
install -D -m 0644 "$B/dnsmasq-usb.conf" /etc/symbios/dnsmasq-usb.conf
install -m 0644 "$B/symbios-usb-gadget.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable symbios-usb-gadget.service
systemctl restart symbios-usb-gadget.service || echo "   the cable link did not come up now; check after a reboot"

echo "== firewall: the cable open; on the WiFi only SSH (22) and the desk (80)"
install -m 0755 "$B/nftables.conf" /etc/nftables.conf
nft -c -f /etc/nftables.conf
systemctl enable nftables.service
systemctl restart nftables.service

echo "== sound: PipeWire for $USER_NAME, running without a login"
loginctl enable-linger "$USER_NAME"   # /run/user/<uid> and the user's services exist from boot
systemctl start "user@$USER_ID.service"
sudo -u "$USER_NAME" XDG_RUNTIME_DIR="/run/user/$USER_ID" systemctl --user enable --now pipewire.socket pipewire-pulse.socket wireplumber.service \
  || echo "   PipeWire did not start now; it starts at the next boot"

echo "== folders: the ones Linux and macOS users know"
# written as Linux's standard folders (~/.config/user-dirs.dirs), so programs and TermNL find them by role;
# the desktop, templates and public folders are this home itself: SymbiOS has none of those.
# Videos: on this chip only WebM plays well (VP8, tested at 360p on the desk, 15 Oct)
sudo -u "$USER_NAME" bash -c "cd '$USER_HOME' && mkdir -p Documents Pictures Music Downloads Videos .config"
cat > "$USER_HOME/.config/user-dirs.dirs" <<'DIRS'
# SymbiOS's folders (install-base.sh)
XDG_DESKTOP_DIR="$HOME"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME"
XDG_PUBLICSHARE_DIR="$HOME"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
DIRS
chown "$USER_NAME:$USER_NAME" "$USER_HOME/.config/user-dirs.dirs"

# (a dry run of the updates was here: on a 1.5 GB board it ran over 7 minutes after printing its list, and looked
# stuck; the blank-card run, 25 Nov. Gab: "I find it extremely long". The timer below says they are on.)
echo "== the automatic security updates: $(systemctl is-enabled apt-daily-upgrade.timer 2>/dev/null || echo off), next $(systemctl show apt-daily-upgrade.timer -p NextElapseUSecRealtime --value 2>/dev/null)"
echo "== done: base layer of $NAME ($(hostname -I | cut -d' ' -f1))"
