# SymbiOS on a Luckfox Lyra Zero W

The same three layers as the Orange Pi (../README.md): the base, TermNL as the foundation on its socket, the desk
on top. Gab, 23 Nov 2026: check "that the architecture we defined for the Orange Pi have been applied exactly the
same way to the Luckfox Lyra". Until then the Lyra ran the desk alone, from `~/dev/desk`, with TermNL loaded
inside it (the desk repository's `board/lyra/install.sh`, which this replaces).

From the laptop, over SSH as root by the laptop's key (since 24 Nov; before, over adb):

```
board/lyra/deploy.sh               # base, termnl, desk; or name the layers to run only those
LYRA=10.55.0.1 board/lyra/deploy.sh desk   # another address: its WiFi one, or the cable's
```

It sends each tree as a commit (`DESK_REF`, default `fold`; `TERMNL_REF`, `symbios`) by content (rsync: only what
changed is written, the SD card spared) to `/var/lib/symbios-src` (root's alone), puts the laptop's SSH key for root
and `lyra`, and runs the installers there as root. The board is known by its own host key (`HostKeyAlias lyra`), read
over the cable on a fresh card: there the first run puts root's key over adb, the card's only way in, and the base
layer then takes adb off the cable for good (the board restarts once). After that there is no password on the board
at all (root and `lyra` locked, `lyra` out of sudo): SSH by the laptop's key, or the card in a card reader.
Gab, 24 Nov: "Root by the laptop's key".

## Same as the Orange Pi

| | |
|---|---|
| TermNL | `/opt/symbios/termnl`, read-only; `termnl.service` on `/run/symbios/termnl.sock` (../foundation) |
| the desk | `/opt/symbios/desk`, read-only; `desk.service` on top of TermNL, the whole home, `--allow all`, the real shell for the board and the cable (../shell) |
| the claim | its keys and owners in `/var/lib/desk-trust` |
| the base | SSH by key only, the firewall (../base/nftables.conf: the cable open, on the WiFi only SSH and the desk), security updates without reboots, British English, the usual folders |

## What the board makes different

| | Orange Pi | Lyra |
|---|---|---|
| the cable | ECM: a phone or a laptop | RNDIS only (adb taken off, 24 Nov): a laptop only (the kernel has no ECM) |
| claiming | the phone on the cable, or the QR code | the QR code a screen on the cable shows; the phone claims over the WiFi |
| WiFi | netplan, through `symbios-wifi` | wpa_supplicant, through the same `symbios-wifi` (TermNL and the desk add and forget networks) |
| screen | HDMI kiosk | none; the e-ink card (address, QR code to join) |
| sound | PipeWire | no sound card |
| Bluetooth | desk-bluetooth | none: WiFi or Bluetooth, not both, on this board's chip (Luckfox forum t=2670; branch lyra-bluetooth parked) |
| models | aarch64 | 32-bit ARM (the desk's `board/lyra/fetch-models.sh`) |
| Mesh | the desk's own (`mesh/`), a radio on its serial port | the desk's own (`mesh/`), a radio over USB (pyusb) |
| name | `symbios` | `lyra` (both on the same WiFi) |

## A fresh card (23 Nov 2026)

Gab: "It should have been wiped clean." The card is written from
`archive/images/Ubuntu_Luckfox_Lyra_Zero_W_MicroSD_202610.img.xz` (sha256 beside it) in the laptop's card reader
(through the hub; `sudo`, so Gab runs it), then, the card back in the board and the board on the cable:

```
WPA=archive/lyra-before-wipe-2026-11-23/carry-wpa.conf MODELS=archive/lyra-before-wipe-2026-11-23/carry-models.tar \
  board/lyra/deploy.sh
```

Nothing of the earlier tests comes back: the board is claimed again by the QR code.

`install-desk.sh` can also carry over a desk set up before SymbiOS on the same card (`~/dev/desk`: its claim and
the person's files, the leftovers kept in `/home/lyra/.before-symbios/`); on a fresh card that step does nothing.
