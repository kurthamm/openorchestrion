# Backup and Recovery

## Goal

The Raspberry Pi should be treated as replaceable hardware. A failed microSD card or Pi should not destroy the music library, metadata, stations, listening history, or configuration.

## Two-layer recovery model

### 1. Application/data backup

Back up frequently:

```text
/var/lib/openorchestrion/
    music/
    metadata/
    history.db
    database/
    stations/
    playlists/
    config/
```

The exact filesystem layout may evolve, but application state must remain separable from the OS.

### 2. Full-system recovery

Maintain either:

- a periodic full-device image; or
- a completely reproducible installation process plus application-data restore.

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

OpenOrchestrion now has two deliberately different database classes.

### `assets/*.json` sidecars: irreplaceable

Each sidecar carries deterministic analysis, provenance/rights, and **curated
descriptive metadata** — titles, composers, genres, moods, themes, favorites.
The curated block is human judgement and cannot be reconstructed from the MIDI
bytes by any amount of re-analysis, so sidecars must be included in every
application-data backup. See [Curating descriptive metadata](metadata-curation.md).

### `catalog.db`: rebuildable

The music catalog is an operational/search index. It can be deleted and regenerated from durable MIDI sidecars. It is convenient to back up, but it is not the only copy of irreplaceable music metadata.

### `history.db`: durable runtime state

Listening history records behavior that cannot be reconstructed from MIDI files or sidecars. It contains queued/started/substantial/completed/skipped/failed playback state, last-played data, play counts, and no-repeat inputs.

`history.db` therefore **must be included in application-data backups** and must survive catalog reindexing.

SQLite databases should be backed up using a database-safe snapshot/backup mechanism rather than copying a file while an active write transaction is in progress.

## Recovery drill

A release is not operationally complete until a restore has been tested:

1. Provision a blank replacement storage device.
2. Restore/reinstall OpenOrchestrion.
3. Restore application data and music.
4. Restore `history.db` and other durable runtime state.
5. Rebuild `catalog.db` from sidecars if needed.
6. Reconnect MIDI devices.
7. Confirm device profiles and routing.
8. Start the appliance.
9. Verify library contents, favorites/history, stations, AI configuration, and playback.
10. Confirm recent-play/no-repeat behavior survived the restore.

## Storage medium

microSD is sufficient for early development. For an always-on appliance, USB SSD boot/storage may improve durability and serviceability. The architecture should not depend on the specific boot medium.
