# Rebuildable SQLite Catalog

OpenOrchestrion uses SQLite as a **search/index layer**, not as the only surviving copy of the music library.

The durable source of truth remains:

```text
<sha256>.mid
<sha256>.json
```

The database can be deleted and recreated from those sidecars at any time.

## Rebuild

```bash
openorchestrion-reindex var/library
```

This creates:

```text
var/library/catalog.db
```

For machine-readable output:

```bash
openorchestrion-reindex var/library --json
```

By default, rebuild is strict. An invalid/corrupt sidecar causes the rebuild to fail **without replacing the last known-good catalog**.

For diagnostic/recovery work, invalid sidecars may be skipped explicitly:

```bash
openorchestrion-reindex var/library --skip-invalid
```

## Atomic replacement

The reindexer builds a temporary SQLite file, validates/indexes all selected sidecars, commits it, then atomically replaces `catalog.db`.

Therefore this sequence is safe:

```text
known-good catalog.db
       │
       ├── build catalog.db.tmp
       │       ├── sidecar 1 ✓
       │       ├── sidecar 2 ✓
       │       └── broken sidecar ✗
       │
       └── original catalog.db remains untouched
```

A bad metadata edit should not take the working appliance catalog down during a rebuild.

## Composition versus performance

OpenOrchestrion distinguishes a **musical composition/work** from a specific MIDI **performance/asset**.

Example:

```text
Composition
Maple Leaf Rag — Scott Joplin
        │
        ├── expressive human-performance MIDI (quality A)
        ├── carefully programmed MIDI (quality B)
        └── score-export MIDI (quality C)
```

Those are three playable assets but one composition.

If curated metadata supplies an explicit `composition_id`, the indexer uses it. Otherwise a stable derived identifier is created from normalized composer + title.

This lets future selection logic say:

> Play Maple Leaf Rag

and then choose the best available performance rather than treating every MIDI rendition as an unrelated song.

## Indexed tables

### `compositions`

Work-level identity:

- composition ID
- title
- composer
- year composed
- era

### `assets`

One row per content-addressed MIDI file:

- SHA-256 / asset ID
- original and stored filenames
- rights/provenance
- title/composer/artist
- performance type and quality grade
- familiarity and energy
- favorite marker (when represented in durable metadata)
- MIDI format/ticks/tracks/duration
- note count/range/velocity summary
- sustain/pitch-bend/SysEx facts
- peak simultaneous MIDI notes
- percussion count
- structural GM assessment
- durable sidecar/MIDI paths

### `asset_tags`

Normalized many-to-many descriptive labels:

- genre
- mood
- theme
- generic tag
- instrumentation

### `asset_channels`

MIDI channels used by an asset and whether each is percussion.

### `asset_programs`

Program Change history including channel, GM program number/name, and Bank Select values.

### `asset_tracks`

Track-level structure including track name, channels, note range/count, Program Change count, and ending tick.

## Query CLI

Basic catalog search:

```bash
openorchestrion-catalog var/library/catalog.db --text "Maple Leaf"
```

Dinner-music style query:

```bash
openorchestrion-catalog var/library/catalog.db \
  --theme dinner \
  --mood relaxed \
  --min-familiarity 3 \
  --max-energy 3
```

Ragtime:

```bash
openorchestrion-catalog var/library/catalog.db --genre ragtime
```

Only material explicitly recorded as open/redistributable:

```bash
openorchestrion-catalog var/library/catalog.db --rights-status verified-open
```

Statistics:

```bash
openorchestrion-catalog var/library/catalog.db --stats
```

JSON output is available with `--json`.

## Familiarity and energy

The initial index normalizes human-friendly values onto a 1–5 scale:

| Metadata | Indexed value |
| --- | ---: |
| `low` | 1 |
| `medium` | 3 |
| `high` | 5 |

Explicit integer values 1–5 are also accepted.

This gives Smart Stations a simple deterministic scale while preserving the more human-readable sidecar representation.

## Sidecar integrity checks

Rebuild validates key invariants before indexing:

- sidecar schema version is supported;
- `asset_id` agrees with SHA-256;
- file SHA and deterministic-analysis SHA agree;
- sidecar filename equals SHA-256;
- stored MIDI filename equals SHA-256;
- the corresponding MIDI object actually exists.

The catalog therefore cannot silently point at a missing or mismatched content object.

## What SQLite does not own

The rebuildable catalog deliberately does **not** become the master copy of curated metadata.

Future user actions such as metadata editing, accepted AI suggestions, favorites, and station definitions must have a durable representation outside a single disposable database file.

Likewise, play history needs a durable strategy before it becomes essential station-selection state. A future implementation may use an append-only event journal or another recoverable state store and then project that state into SQLite.

The architectural rule remains:

> Deleting `catalog.db` must never delete knowledge that cannot be reconstructed from durable OpenOrchestrion data.

## Smart Station boundary

The catalog answers deterministic questions such as:

```text
Which assets are tagged dinner?
Which are low/medium energy?
Which are familiar?
Which are ragtime?
Which use two piano parts?
Which exceed 48 simultaneous MIDI notes?
```

The **Smart Station engine** is the next layer. It will take a structured request, query this catalog, score candidates, apply diversity/no-repeat rules, choose among multiple performances of the same composition, and build a queue.
