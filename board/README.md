# A SymbiOS board, from a blank card

Made and checked on 31 Oct 2026 with an Orange Pi Zero 2W (2 GB) and a 64 GB card, from a laptop
running Linux with a USB card reader.

## 1. The image

Armbian community, Orangepizero2w, Debian trixie, minimal: the build the proof of concept uses,
`Armbian_community_26.11.0-trunk.83_Orangepizero2w_trixie_current_6.18.55_minimal.img.xz`, sha256
`16b7eac792c8f77ed42c857935d346b3f5f96332261cb1254ab587cfac1ec6b3`. It is a nightly build: a newer one
is tried only on purpose, on a second card first.

## 2. The WiFi, before the card is written

A board with no screen has to find the WiFi by itself on its first boot (Armbian asks for it only at
the first login, too late). Put one netplan file per network setup in a folder, for example
`netplan/30-wifis-dhcp.yaml`:

```yaml
network:
  version: 2
  renderer: networkd
  wifis:
    wlan0:
      dhcp4: yes
      regulatory-domain: DE
      access-points:
        "your network":
          password: "its password"
```

Or copy it from a board already running: `scp root@<board>:/etc/netplan/*wifi*.yaml netplan/`.
The folder holds a password: keep it out of any repository.

## 3. Write the card

Insert the card, then find it: `lsblk -d -o NAME,SIZE,TRAN,RM,MODEL`. The card is the removable one on
`usb` with its size (here `sda`, 59.5 G). A laptop's own disk often looks like `mmcblk0` or `nvme0n1`:
never that one.

```
sudo board/write-card.sh /dev/sda <image.img.xz> netplan ~/.ssh/id_ed25519.pub
```

It refuses anything that isn't a removable USB card or the expected image, asks before erasing, writes
the image, then puts the WiFi, the name `symbios` and your SSH key for root on the card.

## 4. First boot and first login

Card in the board, power on. After about two minutes it is on the WiFi; find its address in the
router's list, or look for a new SSH server: the board's name is `symbios`. Then, once:

```
ssh -t root@<address>
```

Armbian asks for a root password, a user and its password, the language (en_GB.UTF-8: TermNL reads
command output with a decimal point; the base layer sets it anyway) and the time zone. Until this is done the root password is
Armbian's default, `1234`, and SSH takes passwords: do it at once.

Then give the user your key: `ssh root@<address> 'install -d -m 700 -o <user> -g <user> /home/<user>/.ssh
&& install -m 600 -o <user> -g <user> /root/.ssh/authorized_keys /home/<user>/.ssh/'`.

## 5. The base layer

```
rsync -a board/ <user>@<address>:symbios-board/
ssh -t <user>@<address> sudo symbios-board/install-base.sh
```

SSH by key only (root too), a firewall (the USB cable open, on the WiFi only SSH and the desk), Armbian's
own packages held and Debian's security fixes installed by themselves, the name `symbios.local`, the
USB cable link at `10.55.0.1` (the board's USB-C port closest to its end), sound, and the folders Documents, Pictures, Music, Downloads, Videos.
Keep an SSH session open while it runs, in case the new SSH settings refuse you.

## 6. The foundation: TermNL

From the laptop, a copy of TermNL (its `symbios` branch, without its history) and which commit it is:

```
ssh <user>@<address> mkdir -p symbios-src
rsync -a --delete --exclude .git --exclude logs --exclude __pycache__ termnl/ <user>@<address>:symbios-src/termnl/
git -C termnl log -1 --format='%h %s' | ssh <user>@<address> 'cat > symbios-src/termnl/COMMIT'
rsync -a board/ <user>@<address>:symbios-board/
ssh -t <user>@<address> sudo symbios-board/install-termnl.sh symbios-src/termnl
```

TermNL in `/opt/symbios/termnl` (read-only), a service at boot answering only on
`/run/symbios/termnl.sock` (no network port; only the user may open it), the person's own files in
`~/.config/termnl`, and a fixed list of what it may do as root: the WiFi (`symbios-wifi`), power off,
restart, restarting a service. Then, on the board or over SSH: `termnl how much space is left?`

The desk, on top, comes next: the README at the top of the repository, "Installing on an Orange Pi Zero 2W", step 3.
