# Backup and Recovery

## Goal

The Raspberry Pi is replaceable hardware. A failed microSD card or Pi must not destroy the music library, curated metadata, rights/provenance, AI enrichment, favorites, or listening history.

OpenOrchestrion therefore separates **application data that must be preserved** from software/configuration that can be recreated or backed up separately.

## Reference durable state

The reference appliance keeps application data under:

```text
/var/lib/openorchestrion/
    library/
        assets/
            <sha256>.mid
            <sha256>.json
            <sha256>.json.lock   # writer synchronization, not backup data
        catalog.db               # rebuildable
    history.db                   # durable listening/runtime history
    setup.json                   # harmless first-run UX state
```

The software environment under `/opt/openorchestrion` is disposable. Service configuration and provider secrets live under `/etc/openorchestrion` and have a separate policy.

## Verified application-data archive

`openorchestrion.backup.create_backup()` implements the versioned application-data archive used by future CLI/UI surfaces. Version 1 is a ZIP whose allowed contents are deliberately narrow:

```text
manifest.json
library/assets/<sha256>.mid
library/assets/<sha256>.json
history.db                         # only when history exists
```

The archive **does not contain**:

- `library/catalog.db`;
- `.json.lock` writer lock files;
- `/etc/openorchestrion/openorchestrion.env`;
- `/etc/openorchestrion/openorchestrion.secrets.env` or provider keys;
- the Python environment or systemd unit;
- arbitrary files placed beside the library.

`setup.json` is intentionally not part of the v1 core archive. It is a harmless wizard preference and can be recreated without losing music or behavior history.

### Manifest

`manifest.json` records:

- format identifier `openorchestrion-data-backup`;
- archive format version;
- UTC creation time;
- every payload path;
- exact uncompressed byte size;
- SHA-256 digest.

The archive is written to a sibling temporary file, fsynced, and atomically renamed over the requested destination only after every snapshot/validation step succeeds. A failed backup therefore never replaces a prior good archive with a partial one.

## Backup validation

A backup is not a blind directory copy.

For every stored MIDI asset, backup requires a matching `.mid` / `.json` pair. It verifies:

- the MIDI bytes hash to the SHA-256 encoded in the filename;
- sidecar `asset_id` matches that digest;
- `file.sha256` matches;
- `file.stored_filename` is `<sha256>.mid`;
- recorded file size, when present, matches the stored object;
- `deterministic_analysis.sha256` matches;
- the staged sidecars can rebuild a strict catalog successfully.

Orphan objects/sidecars, malformed JSON, unexpected files, symlinks, or corrupt content-addressed objects fail the backup rather than producing an archive that merely looks complete.

Metadata edits are atomic sidecar replacements, so the snapshot reads one complete sidecar version. The asset set is inventoried again after staging; an import/removal racing the backup makes the run fail and ask for a retry rather than silently taking an ambiguous library snapshot.

## SQLite history snapshot

`history.db` contains behavior that cannot be reconstructed from MIDI files or sidecars. It therefore belongs in application-data backups.

It is **never copied live as a normal file**. Backup opens the current database and uses SQLite's backup API to create a transactionally consistent standalone snapshot. The snapshot then must pass:

- `PRAGMA quick_check`;
- `PRAGMA foreign_key_check`;
- the current OpenOrchestrion history schema-version check.

This remains correct when the live database is in WAL mode and playback/history writers are active.

## Restore is verify-then-publish

`openorchestrion.backup.restore_backup()` restores only to an **absent or empty** state root. Replacing an active appliance is intentionally outside this core layer because service stop/restart and operator confirmation belong in the later CLI/UI workflow.

Restore treats the archive as untrusted input. It does not call `ZipFile.extractall()` and rejects before publication:

- absolute paths;
- `..` traversal;
- non-canonical/backslash paths;
- duplicate ZIP members;
- duplicate manifest paths;
- symlink/non-regular members;
- unexpected top-level files;
- unexpected payload paths such as `catalog.db` or secrets;
- unsupported manifest format/version;
- manifest/member size mismatch;
- SHA-256 mismatch;
- malformed or identity-mismatched sidecars;
- corrupt/unsupported history SQLite;
- a restore target that became non-empty during validation.

Every member is streamed into a temporary directory created **beside the final state root** and hashed while it is written.

### Catalog rebuild before publication

The catalog is never trusted from backup. After all payloads are extracted and verified, restore runs a strict `rebuild_catalog()` **inside the staging tree**. Only if that succeeds is the complete staging directory atomically renamed into place.

This is deliberately stricter than publishing the data first and rebuilding afterward: a sidecar that passes transport hashes but cannot be indexed never becomes live state. The published restore already contains a freshly rebuilt, disposable `library/catalog.db`.

If any pre-publication step fails, the staging tree is removed and the requested target remains absent/empty. There is no partially restored live tree.

## Two-layer recovery model

### 1. Application/data backup

Use the verified application-data archive frequently. It preserves the pieces that carry real user value:

- immutable MIDI objects;
- curated descriptive metadata and favorites;
- provenance/rights evidence;
- AI enrichment records;
- listening/history/no-repeat state.

### 2. Software/configuration recovery

Reinstall the appliance software from a current package/checkout using the reproducible installation procedure. Back up non-secret `/etc/openorchestrion/openorchestrion.env` separately for convenience.

Provider secrets require a deliberate secret-management policy. They are excluded from the application-data archive by design. Re-enter or restore them through an appropriately protected operator mechanism rather than putting API keys into a music/history ZIP.

A periodic whole-device image can still be useful as an emergency parachute, but the maintainable recovery path is fresh OS + reproducible appliance install + verified application-data restore.

## Cloud backup

Google Drive or another remote destination is suitable for storing completed backup archives because MIDI data is compact. The remote copy is not the live playback filesystem.

Preferred model:

```text
local durable state
        │
        ▼
verified local archive
        │
        ▼
scheduled upload/sync
        │
        ▼
remote backup storage
```

Playback remains local even when the Internet is unavailable.

## Recovery drill

A release is not operationally complete until restore has been tested on blank storage:

1. Provision replacement storage / a clean Raspberry Pi OS installation.
2. Reinstall OpenOrchestrion through the appliance installer.
3. Stop the appliance service before replacing durable state.
4. Restore a verified application-data archive into the blank state root.
5. Restore/re-enter `/etc/openorchestrion` configuration and secrets separately as appropriate.
6. Start the appliance.
7. Run `openorchestrion-smoke`.
8. Verify library count, titles, favorites, provenance, and enrichment.
9. Verify listening history and no-repeat behavior survived.
10. Reconnect MIDI devices and confirm routing/profile behavior.
11. Run the hardware conformance/timing checks appropriate to the reference build.

The later operator CLI/UI should orchestrate service control around the same core `create_backup()` / `restore_backup()` functions rather than implementing a second backup format.

## Storage medium

microSD is sufficient for early development. For an always-on appliance, USB SSD boot/storage may improve durability and serviceability. The architecture and archive format do not depend on the specific boot medium.
