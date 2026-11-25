#!/bin/sh
# The Lyra's cable network for the desk: the phone (or laptop) on the OTG port reaches the desk at
# 10.55.0.1, the address the companion looks for and the desk counts as near. The image's own gadget
# (RNDIS + ADB, /etc/init.d/S60netdevice) stays; this waits for it to set 192.168.123.100, then puts
# 10.55.0.1 first on usb0 (udhcpd answers from the first address) and keeps .100 beside it.
IF=usb0
i=0
while [ $i -lt 60 ]; do
  ip -4 addr show dev $IF 2>/dev/null | grep -q 192.168.123.100 && break
  sleep 1; i=$((i+1))
done
ip addr flush dev $IF
ip addr add 10.55.0.1/24 dev $IF
ip addr add 192.168.123.100/24 dev $IF
ip link set $IF up
mkdir -p /var/lib/misc && touch /var/lib/misc/udhcpd.leases
exec busybox udhcpd -f /etc/desk/udhcpd-usb.conf
