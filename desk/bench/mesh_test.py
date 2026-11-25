"""Mesh's encoding, framing and archive, with no radio: python3 bench/mesh_test.py"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mesh import mesh, wire  # noqa: E402
from mesh.archive import Archive  # noqa: E402


class Wire(unittest.TestCase):
    def test_round_trip(self):
        raw = wire.encode((1, "v", 300), (2, "s", "Pantheon"), (3, "f32", 0xB2DF9083), (4, "v", -5))
        f = wire.decode(raw)
        self.assertEqual(wire.first(f, 1), 300)
        self.assertEqual(wire.text(f, 2), "Pantheon")
        self.assertEqual(wire.first(f, 3), 0xB2DF9083)
        self.assertEqual(wire.sint32(wire.first(f, 4)), -5)

    def test_cut_message(self):
        with self.assertRaises(ValueError):
            wire.decode(wire.encode((2, "s", "hello"))[:-2])


class Setup(unittest.TestCase):
    """What a radio says of itself (FromRadio config, metadata, channel), as config.proto and channel.proto v2.6.7 have it."""
    def test_privacy_from_the_key(self):
        self.assertEqual(mesh.privacy(b""), "open")
        self.assertEqual(mesh.privacy(b"\x00"), "open")
        self.assertEqual(mesh.privacy(b"\x01"), "public")   # Meshtastic's default key (LongFast)
        self.assertEqual(mesh.privacy(b"\x05"), "public")   # simple4: the default key, changed by one byte
        self.assertEqual(mesh.privacy(bytes(range(16))), "private")
        self.assertEqual(mesh.privacy(bytes(range(32))), "private")

    def test_channel_keeps_no_key(self):
        settings = wire.encode((2, "b", bytes(range(32))), (3, "s", "Pantheon"))
        said = mesh.from_radio(wire.encode((10, "b", wire.encode((1, "v", 1), (2, "b", settings), (3, "v", 2)))))
        self.assertEqual(said, {"kind": "channel", "index": 1, "role": 2, "name": "Pantheon", "privacy": "private"})

    def test_lora_part(self):
        lora = wire.encode((1, "v", 1), (2, "v", 4), (7, "v", 3), (8, "v", 3))  # use_preset, MEDIUM_FAST, EU_868, 3 hops
        said = mesh.from_radio(wire.encode((5, "b", wire.encode((6, "b", lora)))))
        self.assertEqual(said, {"kind": "config", "region": "EU_868", "preset": "Medium Fast", "hops": 3})

    def test_lora_defaults_left_out(self):
        said = mesh.from_radio(wire.encode((5, "b", wire.encode((6, "b", wire.encode((1, "v", 1)))))))  # LONG_FAST, UNSET: zeros
        self.assertEqual((said["region"], said["preset"]), ("unset", "Long Fast"))

    def test_device_part_and_firmware(self):
        self.assertEqual(mesh.from_radio(wire.encode((5, "b", wire.encode((1, "b", wire.encode((1, "v", 2))))))),
                         {"kind": "config", "role": "Router"})
        self.assertEqual(mesh.from_radio(wire.encode((13, "b", wire.encode((1, "s", "2.6.11.60ec05e"))))),
                         {"kind": "metadata", "firmware": "2.6.11.60ec05e"})


class Mesh(unittest.TestCase):
    def test_text_packet_reads_back(self):
        to_radio = wire.decode(mesh.text_packet("salut é", to=0x7E1773A0, channel=1, packet_id=42))
        p = mesh.packet(wire.first(to_radio, 1))
        self.assertEqual((p["to"], p["channel"], p["id"], p["port"]), (0x7E1773A0, 1, 42, mesh.TEXT))
        self.assertEqual(p["payload"].decode(), "salut é")

    def test_deframer_skips_log_text(self):
        one, two = mesh.want_config(7), mesh.heartbeat()
        stream = b"INFO | boot\r\n" + mesh.frame(one) + b"\x94 noise" + mesh.frame(two)
        d = mesh.Deframer()
        got = d.feed(stream[:9]) + d.feed(stream[9:20]) + d.feed(stream[20:])
        self.assertEqual(got, [one, two])

    def test_from_radio(self):
        user = wire.encode((1, "s", "!b2df9083"), (2, "s", "Prometheus"), (3, "s", "PROM"))
        node = wire.encode((1, "v", 0xB2DF9083), (2, "b", user), (9, "v", 0))
        said = mesh.from_radio(wire.encode((4, "b", node)))
        self.assertEqual((said["kind"], said["long"], said["short"], said["hops"]), ("node", "Prometheus", "PROM", 0))
        settings = wire.encode((2, "b", b"secret"), (3, "s", "Pantheon"))
        said = mesh.from_radio(wire.encode((10, "b", wire.encode((1, "v", 1), (2, "b", settings), (3, "v", 2)))))
        self.assertEqual(said, {"kind": "channel", "index": 1, "role": 2, "name": "Pantheon", "privacy": "private"})  # the key isn't kept, only what it makes of the channel
        self.assertEqual(mesh.from_radio(wire.encode((7, "v", 99))), {"kind": "ready", "nonce": 99})

    def test_routing(self):
        self.assertIsNone(mesh.routing_error(wire.encode((3, "v", 0))))
        self.assertEqual(mesh.routing_error(wire.encode((3, "v", 5))), "gave up after retries")


class Archives(unittest.TestCase):
    def test_day_with_status(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Archive(folder)
            a.add({"id": 1, "time": 1795339614, "text": "hello", "status": "sending"})
            a.add({"id": 1, "status": "heard"}, when=1795339614)
            day = a.day_of(1795339614)
            with open(os.path.join(folder, day + ".jsonl"), "a") as f:
                f.write('{"id": 2, "te')  # cut by a power loss
            self.assertEqual(a.days(), [day])
            self.assertEqual([(m["text"], m["status"]) for m in a.read(day)], [("hello", "heard")])
            with self.assertRaises(ValueError):
                a.read("../etc")


if __name__ == "__main__":
    unittest.main()
