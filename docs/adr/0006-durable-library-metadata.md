# ADR-0006: Durable library metadata must survive SQLite rebuild

- **Status:** Accepted
- **Decision:** SQLite is an operational/search index, not the sole durable copy of irreplaceable library metadata. Music assets retain exportable/sidecar metadata sufficient to rebuild the catalog.

## Context

The project may accumulate thousands of curated MIDI files, tags, source information, rights data, and compatibility notes. A single damaged database should not destroy that work.

## Consequences

- Filesystem/sidecar metadata is versionable and backup-friendly.
- The database can be regenerated after corruption or migration.
- Runtime-only state such as play history may still live primarily in SQLite but is backed up separately.
- Cloud backup can sync ordinary library content without mounting the cloud store as a live database filesystem.
