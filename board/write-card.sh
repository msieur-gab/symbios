#!/bin/bash
# Writes the Armbian image to an SD card in a USB card reader, then readies it for a first boot with no
# screen: the WiFi networks, the board's name, the laptop's SSH key for root. Run on the laptop, as root:
#     sudo board/write-card.sh <card> <image.img.xz> <folder of netplan files> [ssh public key]
#     sudo board/write-card.sh /dev/sda ~/Downloads/Armbian_…_minimal.img.xz ./netplan ~/.ssh/id_ed25519.pub
# The netplan folder holds the WiFi as /etc/netplan files (see README.md), written by hand or copied from
# a board already running: scp root@<board>:/etc/netplan/30-wifis-dhcp.yaml ./netplan/
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
DEV=${1:?the card, for example /dev/sda}
IMG=${2:?the Armbian image (.img.xz)}
NET=${3:?a folder of netplan files with the WiFi}
KEY=${4:-/home/${SUDO_USER:-$USER}/.ssh/id_ed25519.pub}
NAME=symbios
# the image the proof of concept was made with (README.md): another one is written only on purpose
SUM=16b7eac792c8f77ed42c857935d346b3f5f96332261cb1254ab587cfac1ec6b3

# never anything but a removable card in a USB reader: a laptop's own disk is neither
[ "$(lsblk -dno RM,TRAN "$DEV" | xargs)" = "1 usb" ] || { echo "$DEV is not a removable USB card: stopping"; exit 1; }
ls "$NET"/*.yaml >/dev/null || { echo "no .yaml in $NET: the board would have no WiFi"; exit 1; }
[ -s "$KEY" ] || { echo "no SSH key at $KEY"; exit 1; }
echo "$SUM  $IMG" | sha256sum -c --quiet || { echo "not the expected image; to write it anyway, change SUM above"; exit 1; }
lsblk -dno SIZE,MODEL "$DEV"
read -r -p "Everything on this card will be erased. Type yes to go on: " ok
[ "$ok" = yes ] || exit 1
umount "$DEV"?* 2>/dev/null || true

echo "writing the image (a few minutes)…"
xz -dc "$IMG" | dd of="$DEV" bs=4M conv=fsync status=progress
partprobe "$DEV"; sleep 2

M=$(mktemp -d)
mount "${DEV}1" "$M"
install -m 600 -o root -g root "$NET"/*.yaml "$M"/etc/netplan/
echo $NAME > "$M"/etc/hostname
sed -i "s/\borangepizero2w\b/$NAME/g" "$M"/etc/hosts
install -d -m 700 "$M"/root/.ssh
install -m 600 "$KEY" "$M"/root/.ssh/authorized_keys
ls -l "$M"/etc/netplan
umount "$M"; rmdir "$M"; sync
echo "done: the card can come out"
