#!/usr/bin/env bash
# Started by the desktop autostart: runs the launcher and keeps Chromium open in kiosk mode.
# Closing Chromium (Alt+F4 / Ctrl+W) brings the menu back; the menu's quit button stops everything.
set -u

# Own process group, so `kill 0` below never reaches the desktop session that started us.
if command -v setsid >/dev/null && [ "$(ps -o pgid= -p $$ | tr -d ' ')" != "$$" ]; then
  exec setsid bash "$0" "$@"
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${KIOSK_PORT:-8765}"
LOG="$HOME/.local/state/kiosk/kiosk.log"
mkdir -p "$(dirname "$LOG")"
: >"$LOG"

trap 'kill 0' EXIT
export KIOSK_PARENT_PID=$$  # the quit button sends SIGTERM here

# The launcher server, restarted if it ever stops.
( while true; do python3 "$DIR/launcher.py"; sleep 2; done ) >>"$LOG" 2>&1 &

for _ in $(seq 50); do
  curl -fs -o /dev/null "http://127.0.0.1:$PORT/api/state" && break
  sleep 0.2
done

BROWSER="$(command -v chromium || command -v chromium-browser)"
if [ -z "$BROWSER" ]; then
  echo "Chromium er ikke installeret" >>"$LOG"
  exit 1
fi
PROFILE="$HOME/.config/kiosk-chromium"
case "$BROWSER" in
  # Snap Chromium (Ubuntu) may not write to hidden folders in $HOME.
  /snap/*) PROFILE="$HOME/snap/chromium/common/kiosk-chromium" ;;
esac
EXTRA=()
# Native Wayland (Raspberry Pi OS labwc): under XWayland the kiosk window may not cover the desktop.
if [ -n "${WAYLAND_DISPLAY:-}" ]; then EXTRA+=(--ozone-platform=wayland); fi

# Right after boot the desktop is still coming up, and a Chromium window opened then can end up
# hidden behind it. Wait for the taskbar and give the desktop a moment to settle.
if [ "$(cut -d. -f1 /proc/uptime 2>/dev/null || echo 0)" -lt 120 ]; then
  for _ in $(seq 30); do
    pgrep -x 'wf-panel-pi|lxpanel' >/dev/null && break
    sleep 1
  done
  sleep 5
fi

while true; do
  # After a power cut Chromium would otherwise ask to restore the old pages.
  PREFS="$PROFILE/Default/Preferences"
  if [ -f "$PREFS" ]; then
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS"
  fi

  echo "$(date '+%F %T') Starter Chromium (${XDG_SESSION_TYPE:-?}, WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-}, DISPLAY=${DISPLAY:-})" >>"$LOG"
  "$BROWSER" \
    --kiosk \
    --start-maximized \
    "${EXTRA[@]}" \
    --user-data-dir="$PROFILE" \
    --no-first-run \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=Translate \
    --password-store=basic \
    --overscroll-history-navigation=0 \
    --check-for-update-interval=31536000 \
    --autoplay-policy=no-user-gesture-required \
    "http://127.0.0.1:$PORT/" >>"$LOG" 2>&1
  sleep 1
done
