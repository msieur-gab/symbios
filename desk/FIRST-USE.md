# First use: making the desk yours

What a new owner does once, after the desk runs on their board (`sudo board/install.sh --kiosk`; how to prepare the SD card is still to be written, see `TODO.md`, "A new SD card from the repository"). Written on 2026-10-27, after the first claim with Gab's phone. Why it works this way is in `SECURE-LINK.md`.

**The claim** makes the desk yours: your phone and your board exchange keys, and from then on the desk knows your phone and no other. It happens **once, over the USB cable only**. A phone on the same Wi-Fi can't claim it, so a neighbour, a café's network or a guest can't take your desk. Gab, 2026-10-27: "let us stick for the safer cable claim".

## What you need

- The board, with the desk installed and switched off or on, it doesn't matter.
- An Android phone with a USB-C port and Chrome. (Tested: a Pixel 7. Not tested yet: iPhones, other browsers.)
- A USB-C cable that carries data, not only power. The phone powers the board through it.

## Once, before the claim: install the companion

1. On the phone, open **your companion's address** in Chrome (the one in `desk.conf`, `companion = …`; see the README).
2. Chrome's menu → **Install app** (or **Add to home screen**). Open it from the home screen from now on.

The companion's address is the one written in `desk.conf` (`companion = …`). If you host your own copy of the companion, put its address there, pull on the board and restart the desk.

## The claim, step by step

1. **Turn the phone's Wi-Fi and mobile data off.** Android only sends a page's requests through a network that has internet, and ignores the cable while one is on. A web page can't change that.
2. **Plug the phone into the board** with the cable. The board starts if it was off; give it a minute.
3. **Open the companion.** It looks for the desk at its saved address, then on the cable (`10.55.0.1`) by itself. The dot at the top right turns green: the desk is in reach.
4. On the home screen, a line appears above the apps: **"This desk has no owner yet"**. Tap it.
5. The line says *claiming…*, then *checking…*, and a message says **"This desk is yours"**. The line goes away.
6. A sheet offers **a secret word for this desk**: at least 8 characters, typed twice. **Set it, and write it down somewhere safe**: it is how a new phone takes the desk back if this one is lost (below). LATER skips it; Settings → **Secret word** sets it any time.
7. **Settings** now shows **owner: yours since <today>**.

The check in step 5 is real: the phone and the board each work out the same secret keys and exchange a sealed message. "This desk is yours" only shows if that worked.

## After the claim

- **Give the desk your Wi-Fi**, still on the cable: Settings → **Open the desk itself** → its **System Monitor**, WiFi part (shown near the board only: its screen or the cable) → add your network; or **Give the desk a WiFi over Bluetooth**.
- **Unplug, turn the phone's Wi-Fi back on**, and in Settings tap **Find the desk on this network**. The companion keeps that address for next time; on the cable, it finds the desk by itself again.

## If something goes wrong

| What you see | What it means, what to do |
| --- | --- |
| No "no owner yet" line, the dot stays red | The companion doesn't reach the desk. Check the phone's Wi-Fi **and** mobile data are both off, the cable carries data, and the board had time to start. Settings → type `10.55.0.1` → SAVE also works. |
| "the desk isn't on the cable…" | The claim only goes over the cable: same checks as above. |
| "the claim is made over the USB cable" | The request reached the desk another way (the phone's Wi-Fi is on). Turn it off and claim again. |
| "already claimed" / Settings says **claimed by another phone** | Someone claimed this desk first: if it was you on another phone, see below. Otherwise only the reset frees it. |
| The phone was lost, reset, or the companion's data cleared | Its key is gone with it. Take the desk back with the secret word (below), or reset it. |

## What the claim protects today

Since 2026-10-27, **everything is locked over the Wi-Fi** except finding the desk (`/api/hello`), the claim, and the desk's page itself (its code, not your content). Only your claimed companion reads or changes anything: files, articles, decks, music, memos, the Assistant (TermNL), commands, the Wi-Fi screen, the board's numbers. Anyone else on the same Wi-Fi sees that a desk is there, and nothing more. The board's own screen (HDMI) and a computer showing the desk, on the cable or the Wi-Fi, show a lock screen with a code until your phone allows them (below). Over Bluetooth, giving the desk a Wi-Fi, the trackpad and the slide clicker take only your phone's sealed writes. Anyone near can still read where the board is (its address and Wi-Fi name) and which slide is on show, deck name included.

A companion that hasn't claimed this desk (another phone, or the same phone at another address) keeps what it couldn't send, with the reason "locked".

## Opening the desk on a screen

Once the desk is yours, every screen showing it is locked until your phone says yes: the board's own HDMI screen, a laptop on the cable, a laptop on the Wi-Fi. Gab, 2026-10-27: "hdmi plug need phone approval", "wifi requires phone as well to unlock".

1. The screen shows **This desk is locked** and a 4-digit code.
2. Open the companion on your phone, near the desk (same Wi-Fi, the cable, as usual). Within 15 seconds, a sheet rises from the bottom: **A screen wants to open the desk**, with the same code and where it asks from. Dismissed, it stays as a line on the home; tap it to answer.
3. **Allow it only if the code is the one on that screen.** Tap ALLOW: the screen opens the desk. REFUSE: it says so and stays locked.

Let one in by mistake? On the phone, **Settings → SCREENS OPEN NOW** lists every open screen: tap one to disconnect it, or **Disconnect every screen**. On the desk itself, the **lock** beside the clock locks that screen at once. Either way the screen is back on its lock screen at once.

A screen stays open until the board restarts, and: the HDMI screen until it is unplugged, a laptop on the cable until the cable comes out, a laptop on the Wi-Fi for 12 hours. A code holds 5 minutes, then the screen shows a new one.

## A new phone: taking the desk back

For when your phone is lost, stolen, reset, or the companion's data was cleared. Needs the secret word.

1. Install the companion on the new phone, as the first time.
2. Wi-Fi and mobile data off, plug it into the board, open the companion.
3. The home says **This desk has another owner: yours? take it back**. Tap it, type the secret word, **TAKE IT BACK**.
4. **"This desk is yours again"**: the new phone is the owner. The old phone is shut out at once, and every screen it had let in locks.

After 3 wrong words in a row, the desk makes you wait a minute before the next try, then 2, 4… up to an hour. A restart doesn't shorten the wait.

## No phone and no word: the reset

From a terminal on the board (over SSH, or on its own screen with a keyboard):

    python3 ~/desk/trust.py unclaim

It shows who owns the desk and asks you to type `yes`. Then the desk has no owner and no secret word; your files stay. Claim it again over the cable, as the first time.

## A long memo on a small board

A memo is transcribed on the board itself, one minute at a time, and Activity's bar shows how far the model has read.
While it runs the board is busy: other heavy work (an article made searchable, a deck) waits its turn, and the desk can
answer more slowly. On the Orange Pi a memo takes about half its length. On the Luckfox Lyra (512 MB) it takes about
twice its length (4 min 30 s of sound in 8 minutes, 24 Nov), and each minute of sound uses nearly all the memory the
job is allowed: it works when the board is otherwise quiet. Record long memos when you don't need the desk for a few
minutes, or record them in several shorter parts.

## Where things are kept

- **On the phone:** its key, made in the browser and impossible to read out of it, and the desk's public key, in the companion's storage. Clearing the site's data or uninstalling the companion forgets them.
- **On the board:** `/var/lib/desk-trust/board.pem` (the board's own key, made at its first start), `owners.json` (the phone that owns it), `word.json` (a fingerprint of the secret word, slow to check, never the word itself) and `tries.json` (wrong words in a row). Outside the home folder, readable only by the desk's user.
