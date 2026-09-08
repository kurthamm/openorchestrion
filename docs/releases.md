# Versioned releases and upgrades

Download a numbered release from [GitHub Releases](https://github.com/kurthamm/openorchestrion/releases).
Use release packages for an appliance; use a separate checkout for development.
The source commit and SHA-256 hashes are recorded in each release's `release.json`.

## Install 0.1.0

On Raspberry Pi OS 64-bit with Python 3.11–3.13, download all six release assets
into one directory: the wheel, source distribution, source ZIP, installer,
`release.json` and `SHA256SUMS`. Then:

```sh
sha256sum -c SHA256SUMS
sudo apt update
sudo apt install -y python3-venv python3-pip build-essential libasound2-dev avahi-daemon avahi-utils
sudo sh ./install-appliance.sh --package "$PWD/openorchestrion-0.1.0-py3-none-any.whl" --mode headless
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-smoke
```

Dependencies are installed from the Python package index; this is not an offline OS
image. The source ZIP contains the public documentation/starter files. Open the Pi
address in your browser and use **Music library → Add music**. Acquisition downloads
are separate from installation and require a deliberate button press.

## Upgrade and retain a rollback

1. Keep your current release wheel and matching installer outside `/opt/openorchestrion`.
   For a pre-release development deployment, retain its exact built wheel first.
2. Record whether `openorchestrion-acquire.timer` is enabled/active. Stop that timer
   and its service during the upgrade, and let any browser discovery check finish.
   Wait until playback is stopped before the brief application restart.
3. Create and inspect an application-data backup:

   ```sh
   sudo /opt/openorchestrion/venv/bin/openorchestrion-backup create /srv/backups/before-upgrade.zip
   sudo /opt/openorchestrion/venv/bin/openorchestrion-backup inspect /srv/backups/before-upgrade.zip
   ```

4. Verify the new release checksums and run its installer with the exact new wheel,
   as above. Configuration and application data are preserved. The installer
   prepares the new environment before downtime and restores the previous runtime
   and units if installation or health checks fail.
5. Run the smoke command, inspect the version in Playback & devices, check your
   library/collections and keyboard connection. Restart discovery if necessary:
   `sudo systemctl start openorchestrion-discovery.service`.
6. Restart acquisition only if it was previously configured/active. Do not silently
   opt a new installation into scheduled downloads.

Do not reuse an existing backup filename. Preserve `/etc/openorchestrion` separately
under your operator secret-backup policy; application backups exclude credentials.

## Roll back deliberately

Use the retained installer with `--package /absolute/path/to/previous.whl`, then
verify health and restart previously active discovery/acquisition services. If a
release's notes require data rollback, restore the matching pre-upgrade backup with
the documented [backup/recovery procedure](backup-recovery.md). Restoring older data
replaces changes made since that snapshot. Do not mix an older runtime with an
unsupported newer data format. Version 0.1.0 adds no incompatible admission schema.

## Maintainer publication

Update the project version, `openorchestrion.__version__`, and matching release notes
in one reviewed PR. Merge passing changes, then run **Actions → Publish release →
Run workflow** on `main`. This reruns the complete CI workflow for the selected
commit. Only the publish job receives write permission. It builds the packages and
source bundle, validates version identity, creates `vX.Y.Z`, and uploads the artifacts
and checksums. Existing tags/releases are never overwritten. If publication fails
after tag creation, inspect the partial release and fix it explicitly rather than
moving a public tag. The workflow is intentionally manual, not every main push.
