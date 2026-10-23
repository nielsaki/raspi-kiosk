#!/usr/bin/env bash
# Installs the kiosk launcher for the current user on Raspberry Pi OS (with desktop).
# Run on the Pi from this folder:  ./install.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/kiosk"

echo "› Kopierer filer til $DEST"
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
  if [ -f "$DEST/sites.json" ]; then cp "$DEST/sites.json" "$DEST/sites.json.bak"; fi
  cp -r "$SRC/." "$DEST/"
fi
chmod +x "$DEST/start-kiosk.sh" "$DEST/launcher.py"

if ! command -v chromium >/dev/null && ! command -v chromium-browser >/dev/null; then
  echo "› Installerer Chromium"
  sudo apt-get update
  sudo apt-get install -y chromium || sudo apt-get install -y chromium-browser
fi
if ! command -v nmcli >/dev/null; then
  echo "! nmcli mangler – Wi-Fi-skærmen kræver NetworkManager (standard på Raspberry Pi OS Bookworm og nyere)"
fi

echo "› Starter kiosken automatisk når skrivebordet starter"
mkdir -p "$HOME/.config/autostart"
cat >"$HOME/.config/autostart/kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Kiosk
Exec=$DEST/start-kiosk.sh
Icon=web-browser
Categories=Utility;
X-GNOME-Autostart-enabled=true
EOF
# Same entry in the app menu, to start it again after "Afslut kiosk".
mkdir -p "$HOME/.local/share/applications"
cp "$HOME/.config/autostart/kiosk.desktop" "$HOME/.local/share/applications/kiosk.desktop"

echo "› Giver $USER lov til at skifte Wi-Fi uden adgangskode"
sudo mkdir -p /etc/polkit-1/rules.d
sudo tee /etc/polkit-1/rules.d/50-kiosk-wifi.rules >/dev/null <<EOF
// Lets the kiosk user join Wi-Fi networks from the kiosk menu.
polkit.addRule(function (action, subject) {
  if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 && subject.user === "$USER") {
    return polkit.Result.YES;
  }
});
EOF

if command -v raspi-config >/dev/null; then
  echo "› Auto-login til skrivebordet og ingen skærmslukning"
  sudo raspi-config nonint do_boot_behaviour B4 || true
  sudo raspi-config nonint do_blanking 1 || true
  # Wi-Fi stays switched off until a country is set.
  if [ -z "$(sudo raspi-config nonint get_wifi_country 2>/dev/null || true)" ]; then
    sudo raspi-config nonint do_wifi_country "${WIFI_COUNTRY:-DK}" || true
  fi
fi
sudo rfkill unblock wifi 2>/dev/null || true

echo
echo "Færdig. Genstart for at prøve:  sudo reboot"
echo "Fjern igen med:                $DEST/uninstall.sh"
