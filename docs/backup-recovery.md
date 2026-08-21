# Backup and Recovery

## Goal

The Raspberry Pi should be treated as replaceable hardware. A failed microSD card or Pi should not destroy the music library, metadata, stations, or configuration.

## Two-layer recovery model

### 1. Application/data backup

Back up frequently:

```text
/var/lib/openorchestrion/
    music/
    metadata/
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
Local library / configuration
          │
          ▼
 scheduled backup/sync
          │
          ▼
 Remote backup storage
```

Playback continues from local storage even if the Internet is unavailable.

## Database strategy

SQLite runtime state should be backed up safely, but durable music metadata should also be exportable/rebuildable from the library. The system should not make one SQLite file the only surviving copy of irreplaceable metadata.

## Recovery drill

A release is not operationally complete until a restore has been tested:

1. Provision a blank replacement storage device.
2. Restore/reinstall OpenOrchestrion.
3. Restore application data and music.
4. Reconnect MIDI devices.
5. Confirm device profiles and routing.
6. Start the appliance.
7. Verify library contents, favorites/history, stations, AI configuration, and playback.

## Storage medium

microSD is sufficient for early development. For an always-on appliance, USB SSD boot/storage may improve durability and serviceability. The architecture should not depend on the specific boot medium.
