# Mesh

Meshtastic on the desk, a part of the board: a radio plugged in by USB (or reached over WiFi) is found by itself,
its messages are kept by day, and the **Mesh** window reads and sends them. Gab, 24 Nov: "core to the board actually,
so anyone plugging a single node into it just inherit from its ability".
Python only, with no Node.js; pyusb is needed only when the board's kernel has no serial driver.

Until 24 Nov it was its own repository, `desk-meshtastic`, loaded by the desk as an add-on. Its history came along
into the desk's: `git log 5bb6e10^2` (the paths there are `desk_meshtastic/...`).

## What's in it

| file | what it does |
|---|---|
| `mesh/wire.py` | the protobuf encoding Meshtastic uses, with no protobuf library |
| `mesh/mesh.py` | the client API's messages (FromRadio, ToRadio) and their framing on a line |
| `mesh/link.py` | the line to the radio: serial port, USB through pyusb, or TCP; `VENDORS`, the makers of Meshtastic boards |
| `mesh/radio.py` | keeps the radio connected, tracks nodes and channels, sends text, records what happened to it |
| `mesh/archive.py` | `<home>/Mesh/YYYY-MM-DD.jsonl`, one line per message, each line saved to disk before the next |
| `mesh/routes.py` | its routes under `/api/mesh/`, answered by the desk's server before any add-on's |
| `web/js/apps/core/mesh/mesh.js` | the window: a tab per channel and per direct conversation, the nodes, sending |
| `board/99-desk-meshtastic.rules` | lets the desk's user reach a radio over USB (the `plugdev` group) |

The quick panel's Mesh tile and the tray's glyph read `GET /api/mesh` (`devices.py`): a radio on USB, seen in
`/sys` without opening it.

## On a board

Nothing to do: the board's install puts the udev rule in place and the desk's user in `plugdev` and `dialout`.
`desk.conf` says where the radio is (`mesh_device = auto`, `usb`, `serial`, `/dev/ttyACM0`, `tcp:192.168.1.20`) and,
if wanted, where its messages go (`mesh_folder`, in the home: `Mesh`).

## Alone, to try a radio

From the desk's folder:

```
python3 -m mesh nodes
python3 -m mesh listen --folder ~/Mesh
python3 -m mesh send "hello" --channel 1
```

## Tests

`python3 bench/mesh_test.py`

The field numbers come from meshtastic/protobufs v2.6.7.
It was first tried on a Luckfox Lyra Zero W, whose kernel has no `cdc_acm`, with a XIAO nRF52840 (Prometheus) over USB.
