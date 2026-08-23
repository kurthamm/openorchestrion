# Raspberry Pi appliance installation

OpenOrchestrion can run as a normal development server, but the reference build is a
**boot-to-appliance** installation on Raspberry Pi OS 64-bit. systemd owns the FastAPI
process; an optional desktop autostart launches Chromium only after the local service is
healthy. Headless and touchscreen installations use the same backend and web application.

No Internet connection is required after the software and music library are installed.

## Reference layout

| Purpose | Path |
|---|---|
| Python environment | `/opt/openorchestrion/venv` |
| Service configuration | `/etc/openorchestrion/openorchestrion.env` |
| Durable state root | `/var/lib/openorchestrion` |
| MIDI library + sidecars | `/var/lib/openorchestrion/library` |
| Rebuildable catalog | `/var/lib/openorchestrion/library/catalog.db` |
| Durable play history | `/var/lib/openorchestrion/history.db` |
| backend systemd unit | `/etc/systemd/system/openorchestrion.service` |
| optional LAN-discovery unit | `/etc/systemd/system/openorchestrion-discovery.service` |

The service never depends on a repository working directory. `catalog.db` remains disposable;
sidecars and `history.db` do not.

## Raspberry Pi OS prerequisites

Start with a current Raspberry Pi OS 64-bit installation. For the backend:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip build-essential libasound2-dev
```

For friendly `.local` discovery also install Avahi:

```bash
sudo apt install -y avahi-daemon avahi-utils
```

Discovery is optional. If those packages are absent the installer warns and leaves the main
OpenOrchestrion service running normally.

For the 7-inch touchscreen Appliance Edition also install Chromium:

```bash
sudo apt install -y chromium
```

If installing from a Git checkout, install `git` as well. `build-essential` and
`libasound2-dev` are included because `python-rtmidi` may need to build against ALSA on ARM.

## Install from a Git checkout

Clone/update the repository, then from its root run one of these.

### Headless/LAN-only

```bash
sudo sh src/openorchestrion/deployment/install-appliance.sh \
  --package "$PWD" \
  --mode headless
```

### Touchscreen kiosk

Run this from the desktop user's shell so `$USER` is the account that logs into the Pi desktop:

```bash
sudo sh src/openorchestrion/deployment/install-appliance.sh \
  --package "$PWD" \
  --mode kiosk \
  --kiosk-user "$USER"
```

For a dedicated appliance that should use the reference friendly name, add:

```text
--hostname openorchestrion
```

That option is explicit by design. Without `--hostname`, the installer never changes the
machine's existing hostname.

The installer:

1. creates a non-login `openorchestrion` service user if necessary;
2. adds it to the system `audio` group when that group exists;
3. creates `/var/lib/openorchestrion` and the library directory;
4. creates/updates the isolated virtual environment under `/opt/openorchestrion`;
5. installs the packaged systemd/environment/kiosk/discovery templates from the installed wheel;
6. preserves existing `/etc/openorchestrion` configuration and secrets on updates;
7. enables and starts `openorchestrion.service`;
8. enables the separate Avahi discovery service when Avahi is available;
9. optionally installs the kiosk `.desktop` file for the named desktop user;
10. changes the system hostname only when `--hostname` was explicitly supplied.

It is safe to run the installer again for upgrades. It does **not** delete the library,
history, or an existing environment file.

## Install from a wheel without a checkout

The deployment templates are part of the wheel, not dependent on repository files. Bootstrap
a temporary virtual environment, export them, then run the exported installer against the
same wheel:

```bash
python3 -m venv /tmp/openorchestrion-bootstrap
/tmp/openorchestrion-bootstrap/bin/pip install /path/to/openorchestrion.whl
/tmp/openorchestrion-bootstrap/bin/openorchestrion-deploy \
  --output-dir /tmp/openorchestrion-deploy

sudo sh /tmp/openorchestrion-deploy/install-appliance.sh \
  --package /path/to/openorchestrion.whl \
  --mode headless
```

Use `--mode kiosk --kiosk-user <desktop-user>` for the touchscreen build. Add
`--hostname openorchestrion` only when this Pi is intended to take the reference appliance
hostname.

## Configuration

The reference environment file is:

```text
/etc/openorchestrion/openorchestrion.env
```

Important settings include:

```text
OPENORCHESTRION_LIBRARY_ROOT=/var/lib/openorchestrion/library
OPENORCHESTRION_CATALOG_DB=/var/lib/openorchestrion/library/catalog.db
OPENORCHESTRION_HISTORY_DB=/var/lib/openorchestrion/history.db
OPENORCHESTRION_VIRTUAL_MIDI=0
OPENORCHESTRION_HOST=0.0.0.0
OPENORCHESTRION_PORT=8000
OPENORCHESTRION_LOG_LEVEL=info
```

After editing it:

```bash
sudo systemctl restart openorchestrion.service
sudo systemctl restart openorchestrion-discovery.service 2>/dev/null || true
```

`openorchestrion-serve`, `openorchestrion-kiosk`, and `openorchestrion-smoke` all read this
same file. The discovery service also reads `OPENORCHESTRION_PORT`, so it advertises the port
the backend actually uses. Process environment variables override file values, which is useful
for temporary diagnostics.

### Network boundary

The reference service binds to `0.0.0.0` so phones/tablets on the household LAN can reach it.
There is currently no Internet-facing authentication layer. **Do not port-forward the service
or expose port 8000 directly to the public Internet.**

## Friendly LAN discovery

OpenOrchestrion uses the standard Raspberry Pi OS Avahi/mDNS stack. There is no cloud
registration or account-based discovery.

When Avahi is installed, `openorchestrion-discovery.service` advertises an `_http._tcp`
service named **OpenOrchestrion** on the configured application port. The discovery process is
separate from playback: if Avahi is absent or fails, only the convenience advertisement is
lost. `openorchestrion.service` keeps running.

A machine's `.local` host name comes from its system hostname. On a dedicated reference Pi,
install with:

```bash
sudo sh src/openorchestrion/deployment/install-appliance.sh \
  --package "$PWD" \
  --mode headless \
  --hostname openorchestrion
```

With the default port, mDNS-capable clients can then browse directly to:

```text
http://openorchestrion.local:8000/
```

If `OPENORCHESTRION_PORT` is changed, use that port instead. Some networks or clients block
multicast DNS; the appliance remains reachable by its ordinary LAN IP address in that case.

The installer **never** renames a machine just to make this URL work. Omit `--hostname` when
the Pi already has an identity that should be preserved, and Avahi will advertise that existing
`<hostname>.local` identity instead.

## Boot behavior

`openorchestrion.service` starts at multi-user boot and does not wait for Internet access.
Missing ALSA/MIDI hardware is a normal degraded state: the web application still starts and
reports `no_midi_output` rather than crash-looping.

When enabled, `openorchestrion-discovery.service` is a separate local-network convenience
process. Planned backend stop/restart operations also stop/restart the advertisement, but a
discovery failure does not stop or restart playback.

The kiosk is deliberately separate. `openorchestrion-kiosk` waits on the local
`/api/health` endpoint, finds `chromium`/`chromium-browser`, and then replaces itself with a
full-screen Chromium process. If the backend is slow to start, Chromium waits rather than
showing a connection-error page.

Headless installations simply omit the desktop autostart file. Nothing in the backend depends
on Chromium.

## Verify the installation

Service status:

```bash
systemctl status openorchestrion.service
systemctl status openorchestrion-discovery.service
```

Post-install smoke check:

```bash
/opt/openorchestrion/venv/bin/openorchestrion-smoke
```

It verifies:

- `/api/health`;
- the packaged HTML application shell;
- `manifest.webmanifest`;
- absolute durable-data configuration;
- the configured library/database parent directories.

A missing catalog, absent MIDI keyboard, or unavailable Avahi daemon does not make this smoke
check fail; those are valid initial/degraded appliance states. Discovery can be inspected
separately with normal Avahi tools such as `avahi-browse -art`.

## Logs

The services write through normal stdout/stderr to journald:

```bash
journalctl -u openorchestrion.service
journalctl -u openorchestrion.service -f
journalctl -u openorchestrion.service --since today
journalctl -u openorchestrion-discovery.service --since today
```

No separate application log rotation system is required.

## Library administration on the reference paths

The service user owns `/var/lib/openorchestrion`. Until an administration UI exists, run
library commands as that user, for example:

```bash
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-import-midi \
  /path/to/music \
  --library-root /var/lib/openorchestrion/library

sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-reindex \
  /var/lib/openorchestrion/library
```

The metadata/tagging and re-analysis commands use the same durable library root.

## Updating

From a current checkout, rerun the installer with the same mode. For example:

```bash
git pull --ff-only
sudo sh src/openorchestrion/deployment/install-appliance.sh \
  --package "$PWD" \
  --mode kiosk \
  --kiosk-user "$USER"
```

You do not need to repeat `--hostname` on updates. Omitting it preserves whatever hostname the
machine already has. The virtual environment and service templates update; configuration and
durable state remain. Run the smoke check after an update.

Before a major update, back up sidecars and history as described in
[Backup and recovery](backup-recovery.md).

## Graceful service stop/restart

Use systemd rather than killing Python directly:

```bash
sudo systemctl restart openorchestrion.service
sudo systemctl stop openorchestrion.service
```

FastAPI shutdown stops active playback before closing MIDI outputs, so a normal service
restart does not strand a durable history attempt in the `started` state. The discovery unit
follows these planned service operations.

## Disable or uninstall without deleting music/history

Disable both services:

```bash
sudo systemctl disable --now openorchestrion-discovery.service 2>/dev/null || true
sudo systemctl disable --now openorchestrion.service
```

To remove the software installation while retaining user data:

```bash
sudo systemctl disable --now openorchestrion-discovery.service 2>/dev/null || true
sudo systemctl disable --now openorchestrion.service || true
sudo rm -f /etc/systemd/system/openorchestrion-discovery.service
sudo rm -f /etc/systemd/system/openorchestrion.service
sudo rm -rf /opt/openorchestrion
sudo systemctl daemon-reload
```

For a kiosk build, also remove this file from the desktop user's home directory:

```text
~/.config/autostart/openorchestrion-kiosk.desktop
```

**Do not delete `/var/lib/openorchestrion` during a software uninstall.** It contains the
durable library sidecars and listening history. Keeping `/etc/openorchestrion` also preserves
the local configuration for a later reinstall. Removing OpenOrchestrion does not restore a
previous hostname automatically; host identity is a system setting, not application data.

## Recovery

If the software install is damaged but durable state is intact:

1. disable/stop the service;
2. remove/recreate `/opt/openorchestrion` by rerunning the installer;
3. keep `/var/lib/openorchestrion` and `/etc/openorchestrion` untouched;
4. if `catalog.db` is missing or suspect, rebuild it from the sidecars;
5. start the service and run `openorchestrion-smoke`.

If restoring to a new SD card/Pi, restore the durable sidecars and `history.db` before rebuilding
the catalog. Code and the web UI come from the package; catalog state comes from sidecars.

## Troubleshooting

**Service repeatedly restarts:**

```bash
systemctl status openorchestrion.service
journalctl -u openorchestrion.service -n 200 --no-pager
```

**`openorchestrion.local` does not resolve:** verify that the Pi was explicitly given that
hostname (`hostnamectl --static`), then check `systemctl status avahi-daemon` and
`systemctl status openorchestrion-discovery.service`. The client and network must also support
mDNS. The normal LAN IP address remains a valid fallback.

**UI works but says no MIDI output:** this is an expected degraded state when no keyboard is
connected. Confirm Linux/ALSA enumeration before changing the service.

**Kiosk does not launch:** run
`/opt/openorchestrion/venv/bin/openorchestrion-kiosk` in the desktop user's terminal. It will
report whether the backend never became healthy or Chromium could not be found.

**Kiosk uses the wrong port:** edit `/etc/openorchestrion/openorchestrion.env`; the kiosk and
discovery service read the same `OPENORCHESTRION_PORT` as the backend.
`OPENORCHESTRION_KIOSK_URL` can explicitly override the local kiosk URL when needed.

**Software reinstall needed:** reinstall `/opt/openorchestrion`; do not re-import the music
unless the stored MIDI objects themselves are missing. The sidecar is authoritative.
