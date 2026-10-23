#!/usr/bin/env bash
# Stops the kiosk and removes everything install.sh set up.
set -u

echo "› Stopper kiosken"
pkill -f '[s]tart-kiosk.sh' || true

echo "› Fjerner autostart, programmenu, browserprofil og gemte valg"
rm -f "$HOME/.config/autostart/kiosk.desktop" "$HOME/.local/share/applications/kiosk.desktop"
rm -rf "$HOME/kiosk" "$HOME/.config/kiosk-chromium" "$HOME/snap/chromium/common/kiosk-chromium" "$HOME/.local/state/kiosk"

if [ -f /etc/polkit-1/rules.d/50-kiosk-wifi.rules ]; then
  echo "› Fjerner Wi-Fi-tilladelsen"
  sudo rm -f /etc/polkit-1/rules.d/50-kiosk-wifi.rules
fi

echo
echo "Færdig. Kiosken starter ikke længere. Auto-login er ikke ændret."
