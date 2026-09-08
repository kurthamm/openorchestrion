# Troubleshooting and support

Start with the symptom below. Commands assume the documented systemd installation.

| Symptom | Check and action |
| --- | --- |
| Browser cannot connect | Check service status and run the smoke command below. Use the actual Pi IP and configured port. `.local` additionally requires Avahi/multicast support. |
| Interface works, no sound | Check Playback & devices, keyboard power, USB data cable and MIDI receive port. Virtual mode intentionally produces no sound. Check transport, mute/volume and arrangement details. |
| Device disappears after a pause | Check the keyboard's own Auto Power Off setting. A web setting cannot disable hardware power management. |
| Wrong instrument or missing part | Inspect performance details. Original preserves bank/program events; Piano Only suppresses GM percussion. Vendor sounds, receive range and polyphony remain hardware limits. |
| Fresh library is empty | Follow Getting started. No personal collection ships with the software. A scan can correctly admit zero candidates; inspect its reasons. |
| Imports exist on disk but are absent from Library | A v2 library lists admitted identities only. Reindexing does not promote rejected/unresolved files. Do not delete admission policy to bypass quality. |
| No new music | Inspect acquisition status, timer and logs below. Duplicate and quality exclusions are normal outcomes; source failures have their own diagnostics. |
| Acquisition requires a seed | Existing music and archived exclusions need duplicate-history coverage. Assess and seed that inventory; never initialize it as empty. |
| Backup says retry later | Acquisition holds the shared snapshot lock. Retry after it finishes; do not delete a live lock. |
| Update fails | The installer downloads before stopping, and restores the previous environment/units after installation or startup failure. Resolve the reported disk/network/dependency error before retrying. |
| Kiosk does not launch | Install Chromium; select a real desktop account with `--mode kiosk --kiosk-user "$USER"`. Autostart requires desktop login. Service health is separate from display/input validation. |
| Remote hostname requires login | Expected for the protected tunnel. Verify Access and tunnel health; do not expose router port 8000. |

## Diagnostic commands

```sh
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-smoke --json
systemctl --no-pager status openorchestrion.service
journalctl -u openorchestrion.service -n 100 --no-pager
/opt/openorchestrion/venv/bin/python -m pip show openorchestrion
sudo -u openorchestrion /opt/openorchestrion/venv/bin/openorchestrion-acquire --status
systemctl list-timers openorchestrion-acquire.timer
journalctl -u openorchestrion-acquire.service --since yesterday
uname -a
```

Include exact commit/wheel version, OS/Python, keyboard model, reproduction steps
and observed errors in a bug report. Prefer a synthetic or redistributable minimal
MIDI example. Do not attach your private library, credentials, tunnel tokens,
provider keys or full environment files.
[Report an issue](https://github.com/kurthamm/openorchestrion/issues/new/choose).

Use [backup and recovery](backup-recovery.md) for verified restore, and
[next steps](next-steps.md) for known remaining work.
