# Getting started: SymbiOS on an Orange Pi Zero 2W, from a blank card

Every step, every command, what you will see, and what to answer. Written from a real install from a blank card
(25 Nov 2026). Allow about an hour, most of it waiting.

**Two places, one rule.** Some commands run on your **laptop**, others reach the **board** through SSH. Your
terminal's prompt tells you where you are: `you@your-laptop:~$` is the laptop, `root@symbios:~#` or
`ana@symbios:~$` is the board. Every command below runs **on the laptop** unless it says otherwise. If you find
yourself on the board by mistake, type `exit`.

Wherever you see `<address>`, put the board's address (step 6). Wherever you see `ana`, put the user name you chose
at step 7.

## What you need

- An **Orange Pi Zero 2W** (1 GB to 4 GB; tested on 1.5 GB and 2 GB) and its power supply (USB-C, 5 V 3 A).
- A **microSD card**, 16 GB or more. Everything on it will be erased.
- A **laptop running Linux** with a **USB card reader**.
- A **USB-C cable that carries data** (not a charge-only cable), for the claim at the end.
- A **phone**: Android with Chrome is tested; another browser worked too, in a phone's private space. iPhones are
  not tested yet.
- Your **WiFi's name and password**. The board joins it by itself on its first start.

## 0. Prepare the laptop (once)

The tools the guide uses:

```
sudo apt install git rsync xz-utils parted openssh-client nmap
```

An SSH key, the laptop's key to the board. See if you have one:

```
ls ~/.ssh/id_ed25519.pub
```

If it says `No such file or directory`, make one, pressing Enter at each question:

```
ssh-keygen -t ed25519
```

## 1. Get SymbiOS and the board image

```
git clone https://github.com/msieur-gab/symbios.git
cd symbios
```

Every command from now on runs **in this folder**.

Download the board image from the [release](https://github.com/msieur-gab/symbios/releases/tag/v0.1): the file
`Armbian_community_26.11.0-trunk.83_Orangepizero2w_trixie_current_6.18.55_minimal.img.xz` (336 MB). It is the
Armbian image SymbiOS was tested on; Armbian no longer offers it, so it is kept there. Put it in your Downloads
folder; it is checked before it is written.

## 2. Your WiFi

Make the board's WiFi file from the template:

```
mkdir -p netplan
cat > netplan/30-wifis-dhcp.yaml <<'EOF'
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
EOF
chmod 600 netplan/30-wifis-dhcp.yaml
nano netplan/30-wifis-dhcp.yaml
```

In the editor, replace `your network` and `its password` with yours, **keeping the quotes**. Replace `DE` with
your country's two letters (GB, FR, US…): it sets which WiFi channels are allowed. Save with **Ctrl+O**, **Enter**,
quit with **Ctrl+X**.

This file holds your password. It stays on your laptop: it is never copied to the repository (`.gitignore`) nor to
the board's files.

## 3. Find your SD card

Put the card in the card reader, then:

```
lsblk -d -o NAME,SIZE,TRAN,RM,MODEL
```

You will see something like:

```
NAME          SIZE TRAN RM MODEL
sda             0B usb   1 USB3.0 CRW -SD      <- an empty slot of the reader
sdb          29.7G usb   1 USB3.0 CRW -SD      <- your card
nvme0n1      476.9G nvme  0 Samsung SSD         <- the laptop's own disk: never this one
```

Your card is the line with **`usb`**, **`1`** under RM, and **your card's size**. Here it is `sdb`, so the card is
`/dev/sdb`. Not sure? Run the command once without the card and once with it: the line that appears is the card.
A laptop's own disk is usually `nvme0n1` or `mmcblk0`, never `usb`.

## 4. Write the card

Run this **in a terminal window** (it asks you to type `yes`), with your card in place of `/dev/sdb`:

```
sudo board/write-card.sh /dev/sdb ~/Downloads/Armbian_community_26.11.0-trunk.83_Orangepizero2w_trixie_current_6.18.55_minimal.img.xz netplan ~/.ssh/id_ed25519.pub
```

It asks your laptop's password (sudo), then:

```
29.7G USB3.0 CRW -SD
Everything on this card will be erased. Type yes to go on: yes
writing the image (a few minutes)…
1619001344 bytes (1.6 GB, 1.5 GiB) copied, 49.222 s, 32.9 MB/s
-rw------- 1 root root 1269 Oct  9 01:43 10-dhcp-all-interfaces.yaml
-rw------- 1 root root  240 Nov 25 17:16 30-wifis-dhcp.yaml
done: the card can come out
```

It refuses anything that is not a removable card in a USB reader, and any image other than the tested one. It
writes the image, then your WiFi, the board's name (`symbios`) and your SSH key onto the card.

## 5. First start

Take the card out, put it in the Orange Pi, plug in the power. A light blinks. Give it **about two minutes**: the
first start fills the card and joins your WiFi.

## 6. Find the board on your network

The easiest: your router's list of devices, a new one named `symbios`. Or from the laptop: first your network's
address (the first three numbers of the laptop's own):

```
ip -4 addr | grep inet
```

Say it shows `inet 192.168.1.51/24`: your network is `192.168.1.0/24`. Then list the machines with SSH open:

```
nmap -p22 --open 192.168.1.0/24
```

Try each address it lists:

```
ssh root@192.168.1.29 hostname
```

The board answers `symbios`. That number is your board's `<address>` for the rest of the guide.

The first time, SSH asks `Are you sure you want to continue connecting (yes/no/[fingerprint])?`: type `yes`.

## 7. First login (Armbian asks a few questions, once)

```
ssh -t root@<address>
```

Armbian asks, roughly in this order (the wording changes between versions):

| It asks | Answer |
|---|---|
| a new root password, twice | a password of your choice; write it down |
| the default shell | `1` (bash) |
| a user name | a short name, for example `ana` |
| that user's password, twice | a password of your choice; you will type it for each install step |
| your real name | your name |
| the language and the time zone | yours (SymbiOS sets British English for the system anyway: TermNL reads numbers with a decimal point) |

When the questions are done, you are **on the board** (`root@symbios:~#`). Type `exit` to come back to the laptop.

Until the base layer (step 9), the board still takes passwords over SSH: carry on now.

## 8. Your user gets your key, and SymbiOS goes to the board

With your user name in place of `ana` (it appears five times):

```
ssh root@<address> 'install -d -m 700 -o ana -g ana /home/ana/.ssh && install -m 600 -o ana -g ana /root/.ssh/authorized_keys /home/ana/.ssh/'
ssh ana@<address> whoami
```

It answers your user name, with no password asked: your key works. Then copy SymbiOS onto the board, into a hidden
folder (your WiFi file stays behind):

```
rsync -a --delete --exclude .git --exclude netplan ./ ana@<address>:.symbios-install/
```

## 9. The base layer

```
ssh -t ana@<address> 'sudo .symbios-install/board/install-base.sh'
```

It asks your user's password (sudo). About five minutes. You will see, among others:

```
== SSH: by key only
== firewall: the cable open; on the WiFi only SSH (22) and the desk (80)
== sound: PipeWire for ana, running without a login
== the automatic security updates: enabled, next …
== done: base layer of symbios (<address>)
```

From now on SSH takes **keys only**: your laptop gets in, a password never does.

## 10. TermNL, the foundation

```
ssh -t ana@<address> 'sudo .symbios-install/board/install-termnl.sh .symbios-install/termnl'
ssh ana@<address> termnl how much space is left
```

Under a minute. The board answers in plain words:

```
Plenty of room: 27.1 GB free.
```

## 11. Your companion, the phone's page

Your phone holds the key that owns your board, inside the companion page, which you host yourself (the README
says why). Two ways:

- **GitHub Pages**, if you have a GitHub account: **fork** this repository (the Fork button on GitHub), then in your
  fork **Settings → Pages → Source: GitHub Actions**, then the **Actions** tab → **enable**, then **companion** →
  **Run workflow**. A minute later your companion is at `https://<your GitHub name>.github.io/symbios`. (Every Pages
  site of one account shares one address for the browser: fine if all your Pages are yours and trusted.)
- **Netlify Drop**: drag the `companion` folder from this folder onto
  [app.netlify.com/drop](https://app.netlify.com/drop) and keep the address it gives (`https://<name>.netlify.app`).

Open that address in a browser to check: you see the companion's page.

## 12. The desk

With your companion's address, **keeping the single quotes**:

```
ssh -t ana@<address> 'sudo COMPANION="https://<your companion>" .symbios-install/board/install-desk.sh .symbios-install/desk'
```

The longest step, **10 to 20 minutes**: the packages, the kiosk browser for an HDMI screen, and the speech and
search models (about 300 MB). Among the lines:

```
   1470 MB of memory: heavy jobs held lower (/etc/symbios/desk.conf)     <- on a board under 1.8 GB only
   companion: https://<your companion>
```

The board keeps its own settings in `/etc/symbios/desk.conf`, so running this again later (to update) keeps them.

**Normal:** with no HDMI screen plugged in, the kiosk's service shows as failed; it starts when a screen is plugged.

## 13. Claim it

1. Plug the USB-C data cable into the board's **USB-C port closest to the end of the board**, and into the laptop.
2. In the laptop's browser, open **`http://10.55.0.1`**. It shows a **QR code**. (The QR code shows only to a screen
   near the board: on the cable, or the board's own HDMI screen. Over the WiFi you get the lock screen.)
3. Scan the QR code with your phone. It opens **your companion**, which claims the board.
4. It offers a **secret word**: set it and write it down. It is how a new phone takes the board back if you lose
   this one.
5. The laptop's page asks your phone's permission: **allow** it on the phone if the code matches.

The board is yours: it answers your phone only, and every screen stays locked until your phone allows it. If the
browser offers **Install app** or **Add to home screen** for the companion, do it.

## Afterwards

- **Updating**: in this folder, `git pull`, then step 8's `rsync`, then steps 10 and 12's install lines again (no
  `COMPANION=` needed: the board remembers).
- **Starting over**: write the card again (step 4). The board then has a new SSH identity: before step 6, tell the
  laptop to forget the old one: `ssh-keygen -R <address>`.

## When something goes wrong

| You see | What it means, what to do |
|---|---|
| `… is not a removable USB card: stopping` | That isn't your card. Look again at step 3. |
| `not the expected image` | The image file isn't the tested one, or its download was cut: download it again. |
| `Type yes to go on:` then it stops by itself | It was started from a tool that can't type: run it in a terminal window. |
| `nmap` finds nothing | Wait two more minutes; check the WiFi file's name and password; look at the router's list. |
| `WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!` | The card was written again (a new board identity): `ssh-keygen -R <address>`, then again. |
| `Permission denied (publickey)` | After step 9 the board takes keys only: use the user from step 8, from this laptop. |
| `sudo: https://…: command not found` | The outer single quotes of step 12's line were lost: copy it again, quotes included. |
| A step is quiet for minutes | The base layer's updates and the desk's model downloads take time on a small board. |
| `http://10.55.0.1` doesn't load | The cable is in the other USB-C port, or charges only; one SymbiOS board on the cable at a time. |
| The laptop's page shows a lock, not a QR code | The board is claimed already, or the page came over the WiFi: use the cable. |
