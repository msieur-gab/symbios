#!/bin/bash
# The board as a USB network card (from SymbiOS v1, then the desk): plug its USB port into a computer and
# the board is at http://symbios.local (http://10.55.0.1). Composite gadget, RNDIS (Windows, Linux, Android,
# ChromeOS) + ECM (Mac, Linux), bridged to one segment; a small DHCP server gives the computer
# its address. Nothing else rides on the port: being recognised by anything comes first.
GADGET=/sys/kernel/config/usb_gadget/symbios
BR=usbbr
modprobe libcomposite 2>/dev/null || true

# start clean every time, so a restart always gives the same gadget
if [ -d "$GADGET" ]; then
  cd "$GADGET" || exit 1
  echo "" > UDC 2>/dev/null
  rm -f os_desc/c.1 configs/c.1/*.usb0
  rmdir functions/* configs/c.1/strings/0x409 configs/c.1 strings/0x409 2>/dev/null
  cd / && rmdir "$GADGET" 2>/dev/null
fi

mkdir -p "$GADGET"; cd "$GADGET" || exit 1
echo 0x1d6b > idVendor; echo 0x0104 > idProduct
echo 0x0200 > bcdUSB;   echo 0x0100 > bcdDevice
# IAD/composite device class so Windows binds the multifunction set
echo 0xEF > bDeviceClass; echo 0x02 > bDeviceSubClass; echo 0x01 > bDeviceProtocol
mkdir -p strings/0x409
echo "symbios-001" > strings/0x409/serialnumber
echo "symbios" > strings/0x409/manufacturer
echo "SymbiOS USB" > strings/0x409/product
# Microsoft OS descriptors -> Windows auto-loads the RNDIS driver
echo 1 > os_desc/use; echo 0xcd > os_desc/b_vendor_code; echo MSFT100 > os_desc/qw_sign
mkdir -p configs/c.1/strings/0x409
echo "RNDIS+ECM" > configs/c.1/strings/0x409/configuration
echo 250 > configs/c.1/MaxPower
# RNDIS (Windows / Linux)
mkdir -p functions/rndis.usb0
echo "02:1d:6b:00:00:01" > functions/rndis.usb0/dev_addr
echo "02:1d:6b:00:00:02" > functions/rndis.usb0/host_addr
[ -d functions/rndis.usb0/os_desc/interface.rndis ] && {
  echo RNDIS   > functions/rndis.usb0/os_desc/interface.rndis/compatible_id
  echo 5162001 > functions/rndis.usb0/os_desc/interface.rndis/sub_compatible_id; }
# ECM (Mac / Linux)
mkdir -p functions/ecm.usb0
echo "02:1d:6b:00:00:03" > functions/ecm.usb0/dev_addr
echo "02:1d:6b:00:00:04" > functions/ecm.usb0/host_addr
ln -s functions/rndis.usb0 configs/c.1/
ln -s functions/ecm.usb0   configs/c.1/
ln -s configs/c.1 os_desc
ls /sys/class/udc > UDC
sleep 1
# bridge the gadget netdevs (rndis->usb0, ecm->usb1) into one segment
ip link add name "$BR" type bridge 2>/dev/null || true
for IF in usb0 usb1; do
  if [ -e "/sys/class/net/$IF" ]; then ip link set "$IF" master "$BR" 2>/dev/null; ip link set "$IF" up 2>/dev/null; fi
done
ip addr flush dev "$BR" 2>/dev/null || true
ip addr add 10.55.0.1/24 dev "$BR" 2>/dev/null || true
ip link set "$BR" up 2>/dev/null || true
# DHCP for the computer on the other end
systemctl stop symbios-usb-dnsmasq 2>/dev/null || true
systemctl reset-failed symbios-usb-dnsmasq 2>/dev/null || true
systemd-run --unit=symbios-usb-dnsmasq /usr/sbin/dnsmasq -k --conf-file=/etc/symbios/dnsmasq-usb.conf
