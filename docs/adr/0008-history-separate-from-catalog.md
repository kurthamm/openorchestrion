# ADR-0008: Keep listening history outside the rebuildable catalog

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

OpenOrchestrion's `catalog.db` is intentionally disposable. It is an operational/search index rebuilt from durable MIDI sidecars.

Listening history is different. Facts such as:

- a piece was played 12 days ago;
- a listener skipped after 70 seconds;
- a track has been completed 18 times;
- an item has never been heard;

cannot be reconstructed from the MIDI asset or its descriptive metadata.

If history were stored only in `catalog.db`, a normal reindex would erase household listening behavior and break no-repeat/discovery logic.

## Decision

OpenOrchestrion stores listening history in a separate durable runtime database, currently `history.db`.

The history service records meaningful playback lifecycle events and summary state independently of catalog rebuilding.

`catalog.db` may be regenerated or replaced without reading, modifying, or deleting `history.db`.

`history.db` is application data and must be included in backup/restore procedures.

## Consequences

### Positive

- Catalog rebuilds are safe and stateless with respect to listening behavior.
- No-repeat windows survive metadata reindexing.
- Play counts and last-played data remain durable.
- Recovery responsibilities are explicit: sidecars rebuild the catalog; backups restore history.
- Playback state can evolve without making music metadata the owner of runtime behavior.

### Costs

- The appliance maintains two SQLite databases with different durability semantics.
- Backup tooling must snapshot `history.db` safely.
- Runtime code must resolve asset/composition IDs consistently across the catalog/history boundary.
- Future schema changes require explicit history migrations rather than simply rebuilding the database.

## Rejected alternative: store history in sidecars

Updating music sidecars after every play would create unnecessary writes, mix household runtime behavior with portable music metadata, and make catalog/music backup synchronization noisy.

## Rejected alternative: put history only in `catalog.db`

This violates the core catalog design because `catalog.db` is intentionally replaceable. A reindex would destroy data that cannot be recreated.

## Related decisions

- ADR-0006: Durable library metadata must survive SQLite rebuild.
- ADR-0003: AI interprets intent but never directly drives MIDI.
