# Raspberry Pi kiosk-menu

Ved opstart viser Pi'en en menu i fuld skærm:

1. **Tjekker internet.** Lige efter opstart venter den op til 25 sek. på, at Wi-Fi kommer op af sig selv.
2. **Online → bekræft netværket** ("Forbundet til X – er det det rigtige netværk?"). Spørges én gang pr. opstart,
   og igen hvis netværket skifter. Vælger du selv netværket på Wi-Fi-skærmen, spørges der ikke.
   **Intet internet → Wi-Fi-skærm.** Vælg netværk, skriv adgangskode. "Fortsæt uden internet" bruges, når siden kører lokalt.
3. **Vælg hjemmeside** (fra `sites.json`) eller **Noget andet…** (skriv selv en adresse).
4. **Vælg underside.** Med 10 eller flere sider kommer der et søgefelt; du kan bare begynde at skrive.
5. **Kun for sider med `"allow_other_address": true`:** åbn på den normale adresse, eller skriv en anden
   (fx `192.168.1.20:8000` eller `localhost:5000`). Stien efter `/` er den samme. Adresser brugt før huskes som knapper.

Det sidste valg huskes som en "Seneste"-knap øverst.

## Installation på en Pi

Kræver Raspberry Pi OS **med skrivebord** (Bookworm eller nyere).

Kør i en terminal på Pi'en (eller over `ssh`):

```bash
git clone https://github.com/nielsaki/raspi-kiosk.git
cd raspi-kiosk && ./install.sh
sudo reboot
```

Opdatér til nyeste version:

```bash
cd ~/raspi-kiosk && git pull && ./install.sh
```

`install.sh` kopierer til `~/kiosk`, installerer Chromium hvis den mangler, starter kiosken automatisk,
slår auto-login til og skærmslukning fra, og giver brugeren lov til at skifte Wi-Fi.

## Redigér siderne

Ret `~/kiosk/sites.json` (eller i denne mappe og kør `install.sh` igen). Ændringer gælder næste gang menuen vises.

```json
{
  "name": "Hjemmeside 2",
  "url": "https://example.org",
  "allow_other_address": true,
  "pages": {
    "Forside": "/",
    "Live": "/live"
  }
}
```

Hvis filen har en fejl, viser skærmen linje og kolonne.

## Brug

**Afslut kiosk** (nederst til højre i menuen) stopper kiosken og viser skrivebordet.
Start den igen fra programmenuen ("Kiosk") eller ved at genstarte.

| Tast | Virkning |
| --- | --- |
| **Alt+F4** eller **Ctrl+W** | Lukker siden og viser menuen igen |
| **Alt+←** | Tilbage til menuen (browserens tilbage) |
| **Esc** / **Backspace** | Et trin tilbage i menuen |

## Test på Mac/PC

```bash
KIOSK_FAKE_WIFI=1 python3 launcher.py
# åbn http://127.0.0.1:8765  (adgangskoden "forkert" giver en fejl)
```

## Fejlfinding

- Log: `~/.local/state/kiosk/kiosk.log` (også Chromiums egne fejl)
- Kun skrivebordet ses efter opstart: kiosken venter på skrivebordet og ca. 5 sek. mere, før Chromium åbner.
  Ses den stadig ikke, så send loggen og outputtet af `echo $XDG_SESSION_TYPE; cat /proc/device-tree/model`.
- Gemte valg: `~/.local/state/kiosk/state.json` (slet for at nulstille)
- Fjern det hele igen: `~/kiosk/uninstall.sh`
- Ny version: `git pull && ./install.sh` (ingen grund til at afinstallere først)
