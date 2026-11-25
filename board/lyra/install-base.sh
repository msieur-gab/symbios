#!/bin/bash
# SymbiOS, layer 1 on a Luckfox Lyra Zero W: the base, as ../install-base.sh makes it on the Orange Pi, from
# Luckfox's Ubuntu 22.04 card (Ubuntu_Luckfox_Lyra_Zero_W_MicroSD_202610). The same firewall, SSH settings,
# security updates and folders (the files in ../base); what differs is what the board forces:
# - the cable is RNDIS + udhcpd at 10.55.0.1, beside the image's own ADB gadget (cable/): the Lyra's kernel has
#   no ECM, so a phone can't use the cable (23 Nov). A laptop can; the phone claims by the QR code that the
#   computer on the cable shows (the desk's claim by QR code, 23 Nov)
# - WiFi by wpa_supplicant and systemd-networkd (this image has no netplan), the chip's power saving off
# - the on-board antenna (GPIO 55 at each start: the image takes the external socket, empty here; 24 Nov)
# - no sound card: no PipeWire; no Armbian packages to hold (the kernel isn't from apt)
# - the name lyra: the Orange Pi answers as symbios on the same WiFi
# - root by the laptop's key over SSH, the only way in once this has run: no adb on the cable, the factory passwords
#   locked, lyra out of sudo (Gab, 24 Nov: "Root by the laptop's key"; symbios SECURITY.md, review of 24 Nov, B1, B3)
# - the SD card spared: the journal in RAM, rsyslog off, noatime and commit=60, swappiness 10 (24 Nov: about 1 to
#   1.4 GB of writes a day, all of it logging, against the Orange Pi's 60 MB)
# Board facts behind each step: the brain's knowledge/hardware/luckfox-lyra-zero-w.md.
# Run on the board as root (deploy.sh, over SSH as root), from this folder:
#     install-base.sh [wpa_supplicant file for wlan0]
# Safe to run again: each step leaves alone what is already right.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
USER_NAME="${SUDO_USER:-lyra}"
USER_HOME="$(getent passwd "$USER_NAME" | cut -d: -f6)"
HERE="$(cd "$(dirname "$0")" && pwd)"
B="$HERE/../base"
NAME=lyra
WPA=${1:-}

echo "== time zone (the image comes set to China)"
timedatectl set-timezone Europe/Berlin

echo "== WiFi that lasts (the image keeps it only in /tmp), with power saving off"
if [ -n "$WPA" ]; then install -m 600 -o root -g root "$WPA" /etc/wpa_supplicant/wpa_supplicant-wlan0.conf; fi
if [ -f /etc/wpa_supplicant/wpa_supplicant-wlan0.conf ]; then
  printf '[Match]\nName=wlan0\n\n[Network]\nDHCP=ipv4\n' > /etc/systemd/network/25-wlan0.network
  install -d /etc/systemd/system/wpa_supplicant@wlan0.service.d
  cat > /etc/systemd/system/wpa_supplicant@wlan0.service.d/no-power-save.conf <<'EOF'
[Service]
# the AIC8800 drops off a weak access point with power saving on (Lyra, 2026-11-22)
ExecStartPost=-/bin/sh -c "sleep 2; /usr/sbin/iw dev wlan0 set power_save off"
EOF
  systemctl daemon-reload
  systemctl enable --now systemd-networkd wpa_supplicant@wlan0
  systemctl disable systemd-networkd-wait-online 2>/dev/null || true
else
  echo "   no WiFi file given and none on the board: WiFi left as it is"
fi
# the chip's own power saving drops broadcasts (ARP), so nobody finds the board on WiFi: off from the next boot
if ! grep -q ps_on=0 /usr/bin/wifibt-init.sh; then
  cp -n /usr/bin/wifibt-init.sh /usr/bin/wifibt-init.sh.orig
  sed -i 's|^\(\t*\)if \[ "\$1" = "rk960" \]; then|\1if [ "$1" = "aic8800_fdrv" ]; then\n\1\tinsmod "$1.ko" ps_on=0\n\1elif [ "$1" = "rk960" ]; then|' /usr/bin/wifibt-init.sh
  grep -q ps_on=0 /usr/bin/wifibt-init.sh || echo "   wifibt-init.sh not changed (its text differs): power saving stays on"
fi
# the on-board antenna, from the next start (no antenna in the external socket, its default: Luckfox's wiki)
install -m 644 "$HERE/symbios-antenna.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable symbios-antenna.service
# a fresh card has no network and a wrong clock until the WiFi is up: apt needs both
for i in $(seq 1 30); do ip -4 addr show wlan0 | grep -q inet && break; sleep 2; done
ip -4 -br addr show wlan0
for i in $(seq 1 30); do [ "$(timedatectl show -p NTPSynchronized --value)" = yes ] && break; sleep 2; done
echo "   clock: $(date)"

echo "== the SSH keys are in place before passwords are switched off: root's (the only way to administer) and $USER_NAME's"
[ -s /root/.ssh/authorized_keys ] || { echo "no key in /root/.ssh/authorized_keys: nobody could administer the board (deploy.sh puts the laptop's)"; exit 1; }
[ -s "$USER_HOME/.ssh/authorized_keys" ] || { echo "no key in $USER_HOME/.ssh/authorized_keys: SSH would lock $USER_NAME out (deploy.sh puts the laptop's)"; exit 1; }
chmod 700 /root /root/.ssh  # the image leaves /root readable by all

echo "== packages, from Ubuntu's own mirror (the image's Chinese one is slow from Europe)"
if grep -q mirrors.ustc.edu.cn /etc/apt/sources.list; then
  cp -n /etc/apt/sources.list /etc/apt/sources.list.orig
  sed -i 's|https://mirrors.ustc.edu.cn/ubuntu-ports/|http://ports.ubuntu.com/ubuntu-ports/|' /etc/apt/sources.list
fi
# iw, wireless-tools: the WiFi as TermNL reads it; nftables: the firewall; unattended-upgrades: Ubuntu's security
# fixes; git, rsync: the layers above; curl, bzip2: models; locales: the language below
apt-get -o DPkg::Lock::Timeout=900 update -qq
DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=900 install -y -q --no-install-recommends \
  python3 iw wireless-tools nftables unattended-upgrades git rsync curl bzip2 locales

echo "== language: British English (Gab, 2026-10-31), a decimal point as TermNL reads command output"
locale-gen en_GB.UTF-8 >/dev/null
update-locale LANG=en_GB.UTF-8 LANGUAGE=en_GB:en

echo "== updates: Ubuntu's security fixes only, no reboot by itself"
install -m 0644 "$HERE/52symbios-updates" /etc/apt/apt.conf.d/52symbios-updates

echo "== SSH: by key only"
install -m 0644 "$B/00-symbios-ssh.conf" /etc/ssh/sshd_config.d/00-symbios-ssh.conf
sshd -t
systemctl reload ssh

echo "== name: $NAME"
hostnamectl set-hostname "$NAME"
if grep -q '^127\.0\.1\.1' /etc/hosts; then sed -i -E "s/^127\.0\.1\.1.*/127.0.1.1\t$NAME/" /etc/hosts; else printf '127.0.1.1\t%s\n' "$NAME" >> /etc/hosts; fi

echo "== the cable: the board at http://10.55.0.1 when plugged into a computer (RNDIS, as the image offers it)"
install -m 755 "$HERE/cable/desk-usb-cable.sh" /usr/local/sbin/
install -D -m 644 "$HERE/cable/udhcpd-usb.conf" /etc/desk/udhcpd-usb.conf
install -m 644 "$HERE/cable/desk-usb-cable.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable desk-usb-cable.service
systemctl is-active -q desk-usb-cable.service || systemctl start desk-usb-cable.service

# adb was a root shell, no password, for anyone on the cable (review of 24 Nov, B3). Luckfox's S45usbinit turns it on by
# default; no package owns that file, so updates leave the change in place
echo "== the cable without adb, RNDIS only, from the next start"
if grep -q '^ADB_EN=on$' /etc/init.d/S45usbinit || grep -qx usb_adb_en /etc/.usb_config 2>/dev/null; then
  cp -n /etc/init.d/S45usbinit /etc/init.d/S45usbinit.orig
  sed -i 's/^ADB_EN=on$/ADB_EN=off/' /etc/init.d/S45usbinit
  printf 'usb_rndis_en\n' > /etc/.usb_config
  touch /run/symbios-restart-needed
  echo "   adb taken off the cable: the board restarts at the end (deploy.sh)"
fi

echo "== firewall: the cable open; on the WiFi only SSH (22) and the desk (80)"
install -m 0755 "$B/nftables.conf" /etc/nftables.conf
nft -c -f /etc/nftables.conf
systemctl enable nftables.service
systemctl restart nftables.service

echo "== $USER_NAME's own services run without a login (the desk's heavy jobs, systemd --user)"
loginctl enable-linger "$USER_NAME"
# (no CPU quota here: this kernel has no cpu.max, so the desk holds its heavy jobs to cores 1-2 instead, desk.conf)

echo "== SPI0 for the e-ink card (luckfox-config applies it at boot)"
cp "$HERE/luckfox-config.json" /etc/luckfox-config.json

echo "== folders: the ones Linux and macOS users know"
sudo -u "$USER_NAME" bash -c "cd '$USER_HOME' && mkdir -p Documents Pictures Music Downloads Videos .config"
# written as $USER_NAME, never as root: root following a link the user planted there would write anywhere (B6)
sudo -u "$USER_NAME" tee "$USER_HOME/.config/user-dirs.dirs" >/dev/null <<'DIRS'
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

echo "== the SD card spared: the journal in RAM, rsyslog off, fewer metadata writes, the swap file a last resort"
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nStorage=volatile\nRuntimeMaxUse=16M\n' > /etc/systemd/journald.conf.d/50-symbios-ram.conf
systemctl restart systemd-journald
systemctl disable --now rsyslog 2>/dev/null || true
sed -i -E 's#^(/dev/mmcblk0p3[[:space:]]+/[[:space:]]+ext4[[:space:]]+)rw([[:space:]])#\1rw,noatime,commit=60\2#' /etc/fstab
grep -q 'noatime,commit=60' /etc/fstab || echo "   /etc/fstab not changed (its root line differs)"
mount -o remount,noatime,commit=60 /
printf 'vm.swappiness = 10\n' > /etc/sysctl.d/60-symbios-swap.conf
sysctl -q -p /etc/sysctl.d/60-symbios-swap.conf

# review of 24 Nov, B1: Luckfox's password, unchanged since 2024, with full sudo. SSH takes keys; a board that no longer
# starts is rescued in a card reader
echo "== root only through the fixed list (TermNL's sudoers): $USER_NAME out of sudo and adm, the factory passwords locked"
for g in sudo adm disk docker; do
  if id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx "$g"; then gpasswd -d "$USER_NAME" "$g" >/dev/null; echo "   $USER_NAME out of $g"; fi
done
passwd -l root >/dev/null
passwd -l "$USER_NAME" >/dev/null
rm -rf "$USER_HOME/.symbios-src"  # the old deploy's copy (adb's, open to all), replaced by /var/lib/symbios-src

# (no dry run of the updates here, as ../install-base.sh does: on the Lyra it took over 5 minutes and made the
# board swap, 23 Nov; the updates run by themselves each day)
echo "== done: base layer of $NAME ($(hostname -I | cut -d' ' -f1))"
