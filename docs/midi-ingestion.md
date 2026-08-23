# MIDI Analysis and Ingestion

OpenOrchestrion treats MIDI ingestion as a deterministic pipeline. The application first extracts facts from the MIDI bytes, then stores provenance/rights information, and only later adds curated or AI-inferred descriptive metadata.

## Analyzer

The analyzer is implemented in `openorchestrion.midi.analyzer` and exposed as:

```bash
openorchestrion-analyze path/to/song.mid
```

For machine-readable output:

```bash
openorchestrion-analyze path/to/song.mid --json
```

The first implementation reports:

- SHA-256 and file size
- Standard MIDI File type and ticks per beat
- duration with tempo changes applied
- tempo map and time-signature changes
- track names, event counts, channels, note ranges, and program-change counts
- channels used, with channel 10 percussion called out separately
- note count and global note range
- velocity minimum, maximum, mean, median, and exact histogram
- Program Change events with current Bank Select MSB/LSB and General MIDI program names
- controller numbers, values, channels, and counts
- sustain CC64 usage
- pitch bend, channel aftertouch, and polyphonic aftertouch usage
- SysEx count
- estimated peak simultaneous MIDI notes globally and by channel
- structural compatibility/complexity flags

## Peak simultaneous notes

The analyzer models what a sound engine allocates: **one voice per `(channel, note)`**. Striking a pitch that is already sounding retriggers that voice rather than claiming a second one, so the estimate cannot inflate when ordinary piano writing repeats a pitch under a held pedal.

Two stores are tracked per channel — notes whose key is down, and notes whose key was released while sustain (CC64) was held. Notes released under sustain keep counting until the pedal lifts, so the estimate is more useful for piano material than a simple count of pressed keys. Channel-mode controllers are honoured per channel: All Sound Off (CC120) silences the channel and lifts its pedal; Reset All Controllers (CC121) returns the pedal to its default of up; All Notes Off (CC123) releases the keys but leaves pedal-held notes sounding, exactly as lifting every finger would.

The number is intentionally named **peak simultaneous MIDI notes**, not hardware polyphony. A synthesizer may consume multiple internal oscillator/sample voices for one MIDI note, and voice-stealing behavior differs between engines. The metric is therefore a useful workload estimate, not a promise that a 48-note file will consume exactly 48 voices on a keyboard.

The analysis emits convenience flags for peaks above 24, 32, 48, and 64 notes so the future compatibility engine can quickly identify potentially stressful material for candidate hardware.

Because the figure gates device eligibility through `max_peak_simultaneous_notes`, an over-count does not merely mis-report — it silently removes music from stations. Libraries imported before an analyzer correction carry the old values, so `deterministic_analysis` is re-derived in place with:

```bash
openorchestrion-reanalyze --library-root var/library
```

The MIDI objects are immutable and content-addressed, so nothing is re-imported: only the derived block changes. Curated metadata, provenance and AI enrichment are left untouched, and the catalog is reconciled for each repaired asset. Pass a single asset ID to repair one, or `--no-reindex` to defer the catalog update to `openorchestrion-reindex`.

## General MIDI assessment

The analyzer does not claim that arbitrary MIDI is General MIDI merely because it contains Program Change events.

Current structural assessment values are:

- `gm-compatible-structure` — standard program/percussion structure with no non-zero bank selection observed;
- `extended-or-device-specific-bank` — non-zero Bank Select values indicate an extended or device-specific sound map;
- `undetermined` — insufficient structure to make a useful statement.

SysEx is counted and surfaced separately. Future versions can recognize known safe resets such as GM System On without treating unknown vendor-specific SysEx as executable instructions.

## Synthetic-suite integration

The analyzer is tested against the project's generated conformance fixtures. Examples include:

- `gm-ensemble.mid` → channels 1,2,3,4,5,10; 28 notes; channel-10 percussion; peak six simultaneous notes;
- `note-range.mid` → MIDI notes 0 through 127;
- `polyphony-48.mid` → peak 48 simultaneous notes;
- `sustain-cc64.mid` → sustain detected;
- `two-piano-split.mid` → two independent named piano tracks/channels.

This creates a closed-loop laboratory: OpenOrchestrion knows exactly what the generator wrote and can assert exactly what the analyzer must recover.

## Importer

The first durable importer is implemented in `openorchestrion.library.importer`:

```bash
openorchestrion-import-midi ~/Music/MIDI \
  --library-root var/library \
  --rights-status personal
```

Directories are scanned recursively by default. Multiple files/directories may be supplied in one command.

For verified/open material, provenance can be supplied during import:

```bash
openorchestrion-import-midi piece.mid \
  --library-root var/library \
  --rights-status verified-open \
  --source-label "Mutopia Project" \
  --source-reference "source record or URL" \
  --license "Public Domain" \
  --attribution "Attribution text if required"
```

## Content-addressed storage

Imported MIDI objects are stored by SHA-256:

```text
var/library/
└── assets/
    ├── <sha256>.mid
    └── <sha256>.json
```

This makes duplicate import idempotent. The same MIDI bytes imported twice resolve to the same asset ID instead of creating two library objects.

The importer verifies that an existing object with the same SHA-256 is byte-identical before accepting it as a duplicate.

## Durable sidecar

Each imported MIDI asset receives a JSON sidecar with seven conceptual areas:

```text
schema_version
asset_id
file
provenance
deterministic_analysis
descriptive_metadata
ai_enrichment
```

The separation is deliberate.

### Deterministic analysis

Facts recovered directly from the MIDI file. These should be rebuildable at any time by rerunning the analyzer.

### Descriptive metadata

Human-curated fields such as title normalization, composer, genre, mood, era, theme, familiarity, performance type, and station suitability. This object begins empty rather than pretending a filename is authoritative musical metadata.

### AI enrichment

Future model-suggested metadata. This is a separate list so AI inference never becomes indistinguishable from deterministic MIDI facts or reviewed human metadata.

## Rights default

The importer defaults to:

```text
rights_status = personal
```

OpenOrchestrion never upgrades an unknown/personal file to redistributable merely because it imported successfully. `verified-open` is an explicit provenance assertion that should be supported by source/license evidence.

If a content-addressed asset already has a sidecar, re-import does not silently overwrite its rights metadata. Rights/provenance editing and multi-source provenance will be handled by the library-management layer rather than by accidental re-import.

## Privacy / portability

A durable sidecar does not persist the import machine's absolute source path. The original filename is retained, while deterministic analysis stored in the library references the content-addressed stored filename.

## Schemas

Machine-readable contracts:

- `schemas/midi-analysis.schema.json`
- `schemas/midi-asset.schema.json`

These will be validated in CI as the ingestion model evolves.

## SQLite catalog layer

The rebuildable catalog is now implemented in `openorchestrion.library.catalog`.

```bash
openorchestrion-reindex var/library
```

This scans durable sidecars and creates `var/library/catalog.db`. The build is atomic: an invalid sidecar in strict mode fails the temporary rebuild and leaves the previous known-good database intact.

Basic queries are available through:

```bash
openorchestrion-catalog var/library/catalog.db --theme dinner --max-energy 3
```

The catalog distinguishes compositions from individual MIDI assets/performances, normalizes genres/moods/themes into indexed tag rows, and indexes deterministic MIDI facts needed by future device-compatibility and station-selection logic.

See [catalog.md](catalog.md) for the schema, query examples, rebuild invariants, and the boundary between durable metadata and disposable SQLite state.

## Next layer

The next library milestone is the **Smart Station engine**: take a structured request such as “recognizable dinner music, mostly piano,” query the catalog, score candidates, choose among alternate performances of the same composition, apply diversity/no-repeat policies, and return an explainable queue.
