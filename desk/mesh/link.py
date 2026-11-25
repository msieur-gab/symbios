"""The line to the radio: a serial port, USB without a serial driver, or the network.

  serial  /dev/ttyACM0, /dev/ttyUSB0…: a board whose kernel has the driver (most do). Standard library only.
  usb     a node on USB when the kernel has no cdc_acm (the Luckfox Lyra's): pyusb talks to it directly.
  tcp     host[:4403]: a node with WiFi (ESP32) on the same network.

open_link("auto") takes the first radio it finds, a serial port first, then USB. Only a port that looks like a radio
is asked: a Meshtastic maker's own (VENDORS), then a USB-to-serial chip many boards use instead (SERIAL_CHIPS); never
another device (an Arduino, a GPS) that a question would be written to. Every link has
read(timeout) -> bytes (b"" when nothing came), write(bytes) and close(), and raises OSError when
the line is gone.
"""
import glob
import os
import select
import socket
import termios
import tty

# USB vendors of Meshtastic boards that show a CDC serial port of their own (nRF52, RP2040, ESP32-S3)
VENDORS = {0x239A: "Adafruit", 0x2886: "Seeed", 0x303A: "Espressif", 0x2E8A: "Raspberry Pi", 0x1915: "Nordic"}
# USB-to-serial chips that many Meshtastic boards wear instead of a USB of their own (Gab, 24 Nov: "We need also to
# extend the list to the lilygo and heltec"): Heltec V3 (CP2102), LilyGO T-Beam (CH9102), older boards (CH340, FTDI).
# Their nRF52 and ESP32-S3 boards (T-Echo, T114, Wireless Tracker, T-Deck) already show one of VENDORS.
SERIAL_CHIPS = {0x10C4: "Silicon Labs CP210x", 0x1A86: "WCH CH340/CH9102", 0x0403: "FTDI"}


class SerialLink:
    def __init__(self, path):
        self.name = path
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        tty.setraw(self.fd)
        attrs = termios.tcgetattr(self.fd)
        attrs[4] = attrs[5] = termios.B115200
        attrs[2] |= termios.CLOCAL | termios.CREAD
        termios.tcsetattr(self.fd, termios.TCSANOW, attrs)

    def read(self, timeout=0.5):
        if not select.select([self.fd], [], [], timeout)[0]:
            return b""
        data = os.read(self.fd, 4096)
        if not data:
            raise OSError("the serial port closed")
        return data

    def write(self, data):
        while data:
            select.select([], [self.fd], [], 2)
            n = os.write(self.fd, data)
            data = data[n:]

    def close(self):
        os.close(self.fd)


class TcpLink:
    def __init__(self, address):
        host, _, port = address.partition(":")
        self.name = "tcp:" + address
        self.sock = socket.create_connection((host, int(port or 4403)), timeout=10)

    def read(self, timeout=0.5):
        self.sock.settimeout(timeout)
        try:
            data = self.sock.recv(4096)
        except socket.timeout:
            return b""
        if not data:
            raise OSError("the radio closed the connection")
        return data

    def write(self, data):
        self.sock.settimeout(10)
        self.sock.sendall(data)

    def close(self):
        self.sock.close()


class UsbLink:
    """CDC-ACM spoken from user space: claim the data interface, raise DTR, then bulk in and out."""

    def __init__(self, device):
        import usb.core
        import usb.util
        self.usb, self.core, self.dev = usb.util, usb.core, device
        self.name = "usb:%04x:%04x" % (device.idVendor, device.idProduct)
        config = device.get_active_configuration()
        self.data = next(i for i in config if i.bInterfaceClass == 0x0A)
        control = next((i for i in config if i.bInterfaceClass == 0x02), None)
        for i in (control, self.data):
            if i is not None and device.is_kernel_driver_active(i.bInterfaceNumber):
                device.detach_kernel_driver(i.bInterfaceNumber)
        self.usb.claim_interface(device, self.data.bInterfaceNumber)
        direction = self.usb.endpoint_direction
        self.ep_in = self.usb.find_descriptor(self.data, custom_match=lambda e: direction(e.bEndpointAddress) == self.usb.ENDPOINT_IN)
        self.ep_out = self.usb.find_descriptor(self.data, custom_match=lambda e: direction(e.bEndpointAddress) == self.usb.ENDPOINT_OUT)
        index = control.bInterfaceNumber if control is not None else 0
        device.ctrl_transfer(0x21, 0x22, 0x03, index, None)  # SET_CONTROL_LINE_STATE: DTR and RTS, "someone is listening"

    def read(self, timeout=0.5):
        try:
            return bytes(self.ep_in.read(self.ep_in.wMaxPacketSize * 8, timeout=int(timeout * 1000)))
        except self.core.USBTimeoutError:
            return b""
        except self.core.USBError as e:
            raise OSError(str(e))

    def write(self, data):
        try:
            self.ep_out.write(data, timeout=2000)
        except self.core.USBError as e:
            raise OSError(str(e))

    def close(self):
        try:
            self.usb.release_interface(self.dev, self.data.bInterfaceNumber)
            self.usb.dispose_resources(self.dev)
        except self.core.USBError:
            pass


def port_vendor(path):
    """The USB maker of a serial port (/sys), or None when it isn't on USB or can't be read."""
    here = os.path.realpath("/sys/class/tty/%s/device" % os.path.basename(os.path.realpath(path)))
    for _ in range(4):  # the interface, then the device holding it
        try:
            with open(os.path.join(here, "idVendor")) as f:
                return int(f.read().strip(), 16)
        except (OSError, ValueError):
            here = os.path.dirname(here)
    return None


def serial_ports():
    """The serial ports that look like a radio, a Meshtastic maker's first, then a USB-to-serial chip's."""
    ports = sorted(glob.glob("/dev/serial/by-id/*")) or sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*"))
    makers = [p for p in ports if port_vendor(p) in VENDORS]
    chips = [p for p in ports if port_vendor(p) in SERIAL_CHIPS]
    return makers + chips


def usb_radios():
    """USB devices of a Meshtastic vendor with a CDC data interface that no kernel driver holds."""
    try:
        import usb.core
    except ImportError:
        return []
    found = []
    try:
        for dev in usb.core.find(find_all=True):
            if dev.idVendor not in VENDORS:
                continue
            try:
                if any(i.bInterfaceClass == 0x0A for i in dev.get_active_configuration()):
                    found.append(dev)
            except usb.core.USBError:
                continue  # no right to it (see udev/), or busy
    except usb.core.NoBackendError:
        return []
    return found


def open_link(spec="auto", skip=()):
    """The line to a radio; skip: ports that didn't answer a moment ago, left for the others' turn."""
    if spec.startswith("tcp:"):
        return TcpLink(spec[4:])
    if spec.startswith("/dev/"):
        return SerialLink(spec)
    if spec in ("auto", "serial"):
        for path in serial_ports():
            if path in skip:
                continue
            try:
                return SerialLink(path)
            except OSError:
                continue
    if spec in ("auto", "usb"):
        for dev in usb_radios():
            return UsbLink(dev)
    raise OSError("no radio found (%s)" % spec)
