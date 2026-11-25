# desk (working name)

A small desktop in the browser for a single-board computer. Its look comes from symbios
(window chrome, dock islands, explorer, monitor gauges, Departure Mono, the phosphor theme
by default; a tap on the clock moves to the next theme). Its Assistant is
[TermNL](https://github.com/msieur-gab/TermNL): the terminal in plain words, on the device
itself. The desk server loads it and answers `/api/say`; TermNL understands, asks, and runs
its skills' commands there, except what the page does itself (a file opens in a desk window).
TermNL is a separate project, expected in a `TermNL` folder next to this one; what `--allow`
leaves out it only simulates. ([ptiLU](https://github.com/msieur-gab/ptiLU), the brain before,
is still expected next to it until it is retired.)

```
python3 server.py                 # http://<device>:8800, files and status really run
python3 server.py --allow all     # on a board of its own: sound and power too
python3 server.py --home ~        # work in the real home folder (default: home/ here, a sandbox)
python3 server.py --termnl <path> # TermNL somewhere else
```

- **Assistant**: say something; under each reply, the command and what became of it
  (`ran`, `simulated`, `on the desk`, `failed`). Every sentence goes to TermNL's `logs/`.
- **Articles**: paste a link in the Assistant (or open `http://<desk>/?save=<link>`) and the
  board reads the page, keeps the article and writes it as markdown in `~/Articles`, under the
  front matter brainboard uses (title, url, author, siteName, excerpt, cover, keywords,
  published, savedAt). `article.py` does it, in Python only: `python3-readability` and
  `python3-html2text` from Debian. Sites behind a paywall or a robot check are not kept.
- **Reader**: the library of kept articles and, one at a time, a page to read: symbios's
  Reader styles, markdown drawn by marked (`app/vendor`, MIT) and cleaned of anything that runs.
  Its bar keeps a pasted link too.
- **Files**: the home folder the skills work in; **Edit** opens a file in the Editor.
- **Editor**: plain text, save with the button or Ctrl+S.
- **Music**: walks `~/Music`, plays through the device showing the desk (the board only serves
  the files), keeps playing when its window is closed; covers dithered in the theme colours.
- **Slides**: one folder per deck in `~/Slides`, holding one PDF. Either the slides themselves
  (landscape pages; notes, if any, in a `notes.md`, one block per slide split by `---`), or the
  deck exported as notes pages, each page the slide on top and its notes below: the slides are
  cut out of the pages and the notes written to `notes.md` (`slides.py`). Every screen and the
  phone follow the slide on show; the phone is the remote, with the notes.
  **Tested only with Google Slides' export** (Print preview → "1 slide with notes" → Download as
  PDF, 16:9 slides, 2026-10-21). **Not yet tested:** PowerPoint's Notes Pages and Keynote's
  "slide with notes" PDFs, slides that aren't 16:9, notes running over more than one page.
- **Terminal**: near the board (its own screen, or the USB cable) a real shell, as on symbios:
  bash on a pty, drawn by xterm.js (`app/vendor`, MIT, copied from symbios). Over WiFi, and in
  its **Commands** tab, the log of every command of the session and its output; commands typed
  there go through the same check as the skills'. `--shell` names the networks the shell
  opens for (default: this device only; the board's service adds the cable, `10.55.0.0/24`;
  `--shell off` for none).
- **System Monitor**: the board's numbers, and which groups of commands really run. Near the
  board (its screen, its cable) also its WiFi: the network it is on, the address to open once
  the cable is unplugged, the networks it knows, and a form to add one (`board/desk-wifi`,
  run as root through sudo; added networks live in `/etc/netplan/60-desk-wifi.yaml`). This is
  how a board with no screen is taken somewhere new: plug it into a laptop or a phone (on a
  phone, WiFi and mobile data off while plugged), open `http://10.55.0.1`, add the WiFi there.
- **Making the desk yours**: the first phone plugged in claims it, over the cable only; then the
  desk knows that phone and no other. Step by step for a new owner: `FIRST-USE.md`; the design and
  what is locked so far: `SECURE-LINK.md`.

Three kinds of command:

- **The board** (`mkdir`, `touch`, `df`, `systemctl poweroff`…): sent to `server.py`, which
  runs a command only when it matches a form in `FORMS`. A new skill command needs its
  line there.
- **The desk's own light and sound** (`brightnessctl`, `pactl`): a veil over the page for
  brightness, the player's level for volume. The host's real backlight and system volume
  are left to the host's own keys, on purpose: being plugged into anything and working
  comes first. Timers and reminders also ring in the page.
- **The desk itself** (`x-terminal-emulator`, `xdg-open`, `mousepad`): opened as a window,
  no shell involved. A folder opens in Files, a file in the Editor.

Over USB the board is a network card of both common kinds (RNDIS for Windows, Linux, Android,
ChromeOS; ECM for Mac), as on symbios, and nothing else.

On a board the desk answers at **http://perma.local** (standard web port; `10.55.0.1` over the
cable for hosts that don't resolve `.local` names, such as Android browsers).

On a board: `sudo board/install.sh --kiosk` (service, USB gadget at 10.55.0.1, PipeWire,
and the cog browser on HDMI). See `board/`.

There is no sign-in: anyone on the same network can reach the desk. Standard library only,
no build step: `brain.js` is put together from the ptiLU folder at each page load.
