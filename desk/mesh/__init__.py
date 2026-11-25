"""Mesh: Meshtastic on the desk, a part of the board (Gab, 24 Nov: "core to the board actually, so anyone plugging a
single node into it just inherit from its ability"). A radio on USB, serial or WiFi, its messages kept by day
(archive.py), the routes the Mesh window uses (routes.py). Python only; pyusb when the board's kernel has no serial
driver. Alone, to try a radio: python3 -m mesh (from the desk's folder).
Until 24 Nov its own repository, desk-meshtastic, an add-on; its history came along: git log 5bb6e10^2.
"""
