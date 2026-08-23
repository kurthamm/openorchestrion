# Backup and Recovery

## Goal

The Raspberry Pi should be treated as replaceable hardware. A failed microSD card or Pi should not destroy the music library, metadata, stations, listening history, or configuration.

## Two-layer recovery model

### 1. Application/data backup

The reference appliance keeps durable state under `/var/lib/openorchestrion`:

```text
/var/lib/openorchestrion/
    library/
        assets/
            <sha256>.mid
            <sha256>.json
        catalog.db          # rebuildable
    history.db              # durable listening/runtime history
```

Back up `/var/lib/openorchestrion` frequently. The `assets/*.json` sidecars and
`history.db` are the irreplaceable pieces; the stored MIDI objects are also part
of the local library. `catalog.db` can be rebuilt.

The reference service configuration lives separately at:

```text
/etc/openorchestrion/openorchestrion.env
```

Back it up for convenience, but do not confuse configuration with durable music/history state.
See [Raspberry Pi appliance installation](appliance-install.md) for the reference install and
recovery procedure.

### 2. Full-system recovery

Maintain either:

- a periodic full-device image; or
- the reproducible appliance installation plus application-data restore.

A full image is the emergency parachute. Reproducible software deployment plus data backup is the maintainable long-term strategy.

## Cloud backup

Google Drive or another remote destination is suitable for backup because MIDI files are small. The cloud copy is not the live playback filesystem.

Preferred model:

```text
Local library / configuration / history
          │
          ▼
 scheduled backup/sync
          │
          ▼
 Remote backup storage
```

Playback continues from local storage even if the Internet is unavailable.

## Database strategy

OpenOrchestrion has deliberately different durable and rebuildable data classes.

### `assets/*.json` sidecars: irreplaceable

Each sidecar carries deterministic analysis, provenance/rights, and **curated
descriptive metadata** — titles, composers, genres, moods, themes, favorites.
The curated block is human judgement and cannot be reconstructed from the MIDI
bytes by any amount of re-analysis, so sidecars must be included in every
application-data backup. See [Curating descriptive metadata](metadata-curation.md).

### Stored MIDI objects: durable library content

`assets/<sha256>.mid` is the immutable content-addressed music object that the sidecar describes.
A re-analysis can re-derive deterministic facts from it, but cannot recreate the MIDI bytes if
they are lost. Back up the stored MIDI objects with their sidecars.

### `catalog.db`: rebuildable

The music catalog is an operational/search index. It can be deleted and regenerated from durable MIDI sidecars. It is convenient to back up, but it is not the only copy of irreplaceable music metadata.

### `history.db`: durable runtime state

Listening history records behavior that cannot be reconstructed from MIDI files or sidecars. It contains queued/started/substantial/completed/skipped/failed playback state, last-played data, play counts, and no-repeat inputs.

`history.db` therefore **must be included in application-data backups** and must survive catalog reindexing.

SQLite databases should be backed up using a database-safe snapshot/backup mechanism rather than copying a file while an active write transaction is in progress.

## Software/data separation

The reference software environment lives under `/opt/openorchestrion` and is disposable. A
software repair or upgrade may replace that entire directory without touching the library or
history. Likewise, disabling/removing the systemd unit must not remove `/var/lib/openorchestrion`.

This separation is intentional: the appliance can be rebuilt from a fresh OS plus package while
the durable state is restored independently.

## Recovery drill

A release is not operationally complete until a restore has been tested:

1. Provision a blank replacement storage device.
2. Reinstall OpenOrchestrion using the appliance procedure.
3. Restore `/var/lib/openorchestrion` and, if desired, `/etc/openorchestrion`.
4. Restore `history.db` and the library assets/sidecars.
5. Rebuild `catalog.db` from sidecars if needed.
6. Reconnect MIDI devices.
7. Confirm device profiles and routing.
8. Start the appliance.
9. Run `openorchestrion-smoke`.
10. Verify library contents, favorites/history, stations, AI configuration, and playback.
11. Confirm recent-play/no-repeat behavior survived the restore.

## Storage medium

microSD is sufficient for early development. For an always-on appliance, USB SSD boot/storage may improve durability and serviceability. The architecture does not depend on the specific boot medium.
