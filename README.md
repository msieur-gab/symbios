# SymbiOS

A symbiotic operating system for small boards. The board brings the mind: your files, your notes, your music, your
voice memos, and plain words to run the machine. The screen it is plugged into lends the body: an HDMI screen, a
laptop over a USB cable, your phone. Your files stay on the board: no account, no cloud service, no large model.

<img src="docs/symbios.png" width="720" alt="SymbiOS on an Orange Pi Zero 2W: TermNL answering how much space and memory are left and playing music, beside the music player and a Meshtastic message">

*SymbiOS on an Orange Pi Zero 2W.*

> **An early preview, for builders.** It runs every day on two boards, and it is still young: installing takes a
> laptop, SSH and about an hour. Read "Known limits" before you put your own files on it.
>
> **Installed from a blank card by following its guide** on 25 Nov 2026; a second run with the final guide is next.

## What is inside

| Folder | What it is |
|---|---|
| `termnl/` | **TermNL**, the foundation: you talk to the board in plain sentences ("how much space is left", "play some music", "what is plugged into the USB"). It only ever runs the commands written in its skill files, asks before anything risky, and runs offline. Its own project: [TermNL](https://github.com/msieur-gab/TermNL). |
| `desk/` | **The desk**, the face: a desktop in the browser with Files, Memos (voice memos turned into text on the board), a music Player, Slides, a Reader, search by meaning, Mesh (a Meshtastic radio on USB) and TermNL in a window. The only program that listens on the network. |
| `companion/` | **The companion**, your phone's page: the key that claims the board, the remote, and the same apps in your pocket. A web page you host yourself (below). |
| `board/` | **The installers**: the base system, TermNL as a service on a local socket, the desk on top. |

## Boards

| Board | State |
|---|---|
| **Orange Pi Zero 2W**, Armbian | the main board: HDMI kiosk, sound, Bluetooth, the USB cable to a phone or a laptop. **Tested and working on the 1.5 GB and the 2 GB models** (memory): the 2 GB runs every day since October, the 1.5 GB was installed from a blank card with the guide; the installer lowers the heavy jobs' limits by itself under 1.8 GB. Guide below. |
| **Luckfox Lyra Zero W** (464 MB), Luckfox's Ubuntu image | runs it all, slower; no screen, no sound, WiFi or Bluetooth but not both (a limit of its chip). For the adventurous: `board/lyra/README.md`. |
| **Raspberry Pi** | not yet: it is next. |

You also need a microSD card (16 GB or more), a laptop running Linux with a card reader, a USB-C cable that carries
data, and an **Android phone with Chrome** (iPhones are not tested yet).

## The companion: host your own

Your phone keeps the key that owns your board, inside the companion page. The key never leaves the phone, but
whoever controls the site that serves the page controls what can use that key. So each person hosts their own copy,
over HTTPS (a phone only installs a page from there), in one of two ways:

- **GitHub Pages**, the easiest once you have forked this repository: in your fork, **Settings → Pages → Source:
  GitHub Actions**, then the **Actions** tab → enable, then run **companion** once. Your companion is then at
  `https://<you>.github.io/symbios/`, published again by itself at every push. One thing to know: every Pages site of
  one account shares one address for the browser (`https://<you>.github.io`), so any other page you publish on Pages
  could use your key too. Fine if they are all yours and trusted; for full separation, use a GitHub account or
  organisation for this alone, or Netlify.
- **Netlify Drop**, an address of its own: drag the `companion/` folder onto
  [app.netlify.com/drop](https://app.netlify.com/drop) and keep the address it gives you (`https://<name>.netlify.app`).
  Cloudflare Pages works the same way.

Whichever you choose, the board learns the address once, when the desk is installed (`COMPANION=…`, below), and its
claim QR code opens it.

Never delete that site while your board names it: someone else could take the freed name.

## Installing on an Orange Pi Zero 2W

**Follow [docs/getting-started.md](docs/getting-started.md)**: every command, what you will see and what to answer,
written from a real install from a blank card. In short, from a laptop running Linux:

1. Write the tested Armbian image to the card with your WiFi and SSH key (`board/write-card.sh`).
2. Start the board, find it on your WiFi, answer Armbian's first-login questions.
3. Copy SymbiOS to the board and install its three layers: the base, TermNL, the desk.
4. Host your companion (GitHub Pages or Netlify), give its address to the desk's installer.
5. Plug the USB cable, open `http://10.55.0.1`, scan the QR code with your phone: the board is yours.

## Known limits

- **Claim it at home**, on a network you trust, with no other site open in the laptop's browser on the cable. The QR
  claim isn't bound to your phone's key yet: someone on the same WiFi at that very moment could get in between.
- **The SD card is not encrypted, on purpose**: if you lose your phone, you can still read your files in any card
  reader. The same goes for a stolen board: anyone with the card can read it. If it is lost, release it from your
  phone.
- The board's user can still become root with its password; the programs themselves are installed read-only, and
  TermNL only runs what its skill files allow.
- Mesh stops until the desk restarts if a malformed packet arrives from the mesh.
- The installers download what they need from Debian, PyPI, GitHub and Hugging Face; the board image and the
  models are kept in the release, in case those sources change.
- A deploy guide for the Lyra in this repository's layout, a one-command install and ready-made card images are to
  come.

## Credits and licence

SymbiOS stands on the work of many people: NVIDIA's Parakeet and sherpa-onnx for speech, MiniLM for search, xterm.js,
marked, Meshtastic's message format, Armbian, Debian and more. All are named in [NOTICE.md](NOTICE.md).

Copyright © 2026 Gabriel Baude. Free software under the [GPL-3.0](LICENSE), with two additional terms
([NOTICE.md](NOTICE.md)): copies keep "Originally made by Gabriel Baude" with a link here, and a changed version
carries another name (it may say "based on SymbiOS"). Get in touch through [thecu.be](https://thecu.be).

`VERSIONS` says which version of each part this release holds.
