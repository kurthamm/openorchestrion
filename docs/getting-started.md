# Start using OpenOrchestrion

OpenOrchestrion sends MIDI instructions to a keyboard's sound engine. It does not
synthesize audio in your browser. Virtual playback tests controls without sound.

The public repository does **not** contain the reference owner's 5,861-song
personal library. It includes 18 separately licensed starter files (16 older score exports and two
new qualified ensemble derivatives) for
exploration and testing. Redistribution rights and expressive listening quality
are separate: the 16 older exports are not a promise of v2 qualification.

## Install on a Raspberry Pi

Use Raspberry Pi OS 64-bit and Python 3.11–3.13 (the tested versions).
A headless installation is sufficient; the touchscreen is optional.

```sh
sudo apt update
sudo apt install -y git python3-venv python3-pip build-essential libasound2-dev avahi-daemon avahi-utils
git clone https://github.com/kurthamm/openorchestrion.git
cd openorchestrion
sudo sh src/openorchestrion/deployment/install-appliance.sh --package "$PWD" --mode headless
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-smoke
hostname -I
```

Open `http://<Pi-IP>:8000/` on the same network using the actual Pi address.
For a touchscreen, complete the desktop/Chromium steps in
[appliance installation](appliance-install.md).

## Add your first music

In the browser, open **Music library → Add music**. Start with the preselected
recorded-piano source or choose other available sources, then press **Find qualifying
music**. The server prepares a genuinely empty library and shows progress and results.
You can leave the page while it works. See [guided acquisition](guided-acquisition.md).
The terminal commands below remain available for operators.

For a **new empty library**, initialize the quality policy and run a bounded scan:

```sh
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-acquire --init-empty
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-acquire --source smd --limit 5
```

Refresh Library when the scan finishes. Five candidates does not mean five
admissions: downloads must pass quality and duplicate checks. No private deployment
files are required. An existing collection is refused by `--init-empty`; follow
[quality publication](library-quality-publication.md) and
[acquisition setup](automatic-acquisition.md) to preserve its prior decisions.
Enable the documented timer for regular additions. Installation does not silently
opt you into scheduled Internet downloads.

To explore the older redistributable starter set in a separate development library,
follow [starter-catalog.md](../music/starter-catalog.md). Do not import it over an
existing curated appliance as an installation test.

## Connect a keyboard and listen

1. Power on the keyboard and connect its documented USB MIDI device port to the Pi
   with a data cable. A USB flash-drive socket is a different connection.
2. Open **Playback & devices** and check that MIDI output is ready. The
   [hardware matrix](supported-hardware.md) distinguishes manufacturer evidence
   from physical project tests.
3. Open Library, select a performance and use Play. Inspect its arrangement,
   instruments and compatibility details if it sounds different than expected.
4. Set a comfortable keyboard volume. UI volume scales MIDI dynamics independently
   of the physical amplifier knob.
5. Save favorites and playlists. The server preserves queues/settings across
   restart; browsers can close while music keeps playing.

Use [troubleshooting](troubleshooting.md) for silence, missing devices, updates and
recovery. Configure [backups](backup-recovery.md) before building a substantial
personal collection.

## Try without hardware

From a Linux checkout with the build prerequisites installed:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
export OPENORCHESTRION_ENV_FILE="$PWD/var/development.env"
export OPENORCHESTRION_LIBRARY_ROOT="$PWD/var/development-library"
export OPENORCHESTRION_CATALOG_DB="$OPENORCHESTRION_LIBRARY_ROOT/catalog.db"
export OPENORCHESTRION_HISTORY_DB="$PWD/var/development-history.db"
export OPENORCHESTRION_PLAYER_STATE_DB="$PWD/var/development-player.db"
export OPENORCHESTRION_VIRTUAL_MIDI=1
export OPENORCHESTRION_HOST=127.0.0.1
export OPENORCHESTRION_PORT=8765
mkdir -p "$OPENORCHESTRION_LIBRARY_ROOT"
openorchestrion-import-midi --from-csv music/starter/catalog.csv --library-root "$OPENORCHESTRION_LIBRARY_ROOT"
openorchestrion-tag --from-csv music/starter/tags.csv --library-root "$OPENORCHESTRION_LIBRARY_ROOT"
openorchestrion-reindex "$OPENORCHESTRION_LIBRARY_ROOT"
openorchestrion-serve
```

Open `http://127.0.0.1:8765/`. Explicit paths and port keep development separate
from an appliance already installed on the machine. Virtual mode produces no sound.

The application trusts the household LAN. Remote access needs an authenticated
proxy such as the [documented Cloudflare setup](cloudflare-remote-access.md).
The public GitHub Pages project site is documentation, not a playback server.
