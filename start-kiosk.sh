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

while true; do
  # After a power cut Chromium would otherwise ask to restore the old pages.
  PREFS="$PROFILE/Default/Preferences"
  if [ -f "$PREFS" ]; then
    sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"[^"]*"/"exit_type":"Normal"/' "$PREFS"
  fi

  "$BROWSER" \
    --kiosk \
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
    "http://127.0.0.1:$PORT/" >/dev/null 2>&1
  sleep 1
done
