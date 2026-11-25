#!/bin/bash
# Run by udev when a screen is plugged in or out: start the kiosk with a screen, stop it without.
# A screen also blinks out for a moment when it changes mode or input (a projector, 2026-10-16: out
# and back within half a second), and stopping the kiosk then left a frozen picture until it came
# back. So a screen that goes is only believed 3 s later, when the status is read again; the check
# runs through systemd-run, since udev kills anything that takes long. More events in those seconds
# find the check already waiting and leave it to read the end of the story.
# A screen that comes back to a kiosk still running is turned on by cage at its own preferred mode
# (1080p): the check then puts it back at 720p, as desk-kiosk.service does when it starts.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
connected() {
  for s in /sys/class/drm/card*/card*-HDMI*/status; do
    [ -r "$s" ] && [ "$(cat "$s" 2>/dev/null)" = connected ] && return 0
  done
  return 1
}
if [ "${1:-}" = settled ]; then
  if ! connected; then systemctl --no-block stop desk-kiosk.service
  elif systemctl -q is-active desk-kiosk.service; then
    who=$(systemctl show -p User --value desk-kiosk.service)
    runuser -u "$who" -- env XDG_RUNTIME_DIR=/run/user/"$(id -u "$who")" WAYLAND_DISPLAY=wayland-0 \
      wlr-randr --output HDMI-A-1 --mode 1280x720 || true
  fi
  exit 0
fi
# a board that boots with no screen tries the kiosk four times, then systemd refuses starts for the rest
# of 90 s; a screen plugged in then is a reason to try again, so the refusal is cleared first
if connected && ! systemctl -q is-active desk-kiosk.service; then
  systemctl reset-failed desk-kiosk.service 2>/dev/null
  systemctl --no-block start desk-kiosk.service
fi
# AccuracySec: a timer may otherwise fire up to a minute late
systemd-run --quiet --collect --unit=desk-hdmi-settle --on-active=3 --timer-property=AccuracySec=100ms "$0" settled 2>/dev/null || true
