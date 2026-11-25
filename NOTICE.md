# Notice

SymbiOS is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
License, version 3 (see `LICENSE`), with the additional terms below. It comes with NO WARRANTY, to the extent
permitted by law.

Copyright © 2026 Gabriel Baude.

## Additional terms (GPL-3.0, section 7)

- **Attribution (section 7(b)).** Anyone who conveys SymbiOS, modified or not, must keep the author attribution
  "Originally made by Gabriel Baude", with a link to the original source (https://github.com/msieur-gab/symbios),
  in the About section of the desk and of the companion (or wherever the conveyed work shows its legal notices), and
  in this file.
- **The name (sections 7(c) and 7(e)).** This licence grants no right to use the name "SymbiOS" as a trade name or
  mark. A modified version must be marked as different from the original and carry a different name; it may say it
  is "based on SymbiOS".

## Parts made by others

SymbiOS stands on the work of many people. Each part keeps its own licence, which stays with it.

### In this repository

| What | By | Where | Licence |
|---|---|---|---|
| marked v12.0.2, the Markdown reader | Christopher Jeffrey and contributors | `desk/web/js/lib/marked.min.js`, `desk/app/vendor/`, `companion/marked.min.js` | MIT (in the file's header) |
| xterm.js and its fit add-on, the terminal | the xterm.js authors, SourceLair Private Company, Christopher Jeffrey | `desk/web/js/lib/xterm/`, `desk/app/vendor/` | MIT (below) |
| Departure Mono, a typeface | Helena Zhang, Tobias Fried | `*/fonts/DepartureMono-*` | MIT, `DepartureMono-LICENSE.txt` beside it |
| Instrument Sans, a typeface | Rodrigo Fuenzalida, Jordan Egstad | `desk/web/fonts/InstrumentSans-latin.woff2` | SIL Open Font License 1.1, `InstrumentSans-README.md` beside it |
| Meshtastic's message format (the field numbers of meshtastic/protobufs v2.6.7, read by the desk's own Mesh code) | Meshtastic LLC and contributors | `desk/mesh/` | the protobufs are GPL-3.0 |

### Downloaded by the installers onto the board

| What | By | Licence |
|---|---|---|
| Parakeet TDT 110M, the speech model that turns memos into text | NVIDIA (NeMo) | CC-BY-4.0 |
| sherpa-onnx, which runs it | k2-fsa, Next-gen Kaldi | Apache-2.0 |
| Silero VAD, which finds where speech is in a recording | Silero Team | MIT |
| all-MiniLM-L6-v2, the model behind search by meaning (its ONNX version by Xenova) | sentence-transformers (from Microsoft's MiniLM) | Apache-2.0 |
| ONNX Runtime | Microsoft | MIT |
| NumPy | the NumPy developers | BSD-3-Clause |

### Installed from the board's own system

The board runs on **Armbian** (Orange Pi) or **Luckfox's Ubuntu image** (Luckfox Lyra), both built on the **Linux**
kernel and on **Debian** and **Ubuntu**. From them SymbiOS uses, among others: **Python** and its libraries
cryptography, dbus-next, html2text, lxml, python-qrcode, readability-lxml and pyusb; the
kiosk's browser **cog** and **cage** with **WPE WebKit**, **wlroots**, **GStreamer** and **Mesa**; **PipeWire** and
**WirePlumber** for sound; **BlueZ** for Bluetooth; **wpa_supplicant**, **dnsmasq**, **Avahi** and **nftables** for
the network; **FFmpeg** and **Poppler** for sounds and documents; **systemd**. Each is under its own licence, written
on the board in `/usr/share/doc/<package>/copyright`.

Meshtastic® is a registered trademark of Meshtastic LLC; SymbiOS reads its radios' messages and is not made or
endorsed by it.

### The MIT License (xterm.js)

Copyright (c) 2017-2019, The xterm.js authors (https://github.com/xtermjs/xterm.js)
Copyright (c) 2014-2016, SourceLair Private Company (https://www.sourcelair.com)
Copyright (c) 2012-2013, Christopher Jeffrey (https://github.com/chjj/)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
