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

For verified/open material, the evidence is supplied during import and is audited
before anything is written:

```bash
openorchestrion-import-midi piece.mid \
  --library-root var/library \
  --rights-status verified-open \
  --source-label "Mutopia Project" \
  --source-reference "https://example.org/piece-record" \
  --license CC0-1.0 \
  --license-url "https://creativecommons.org/publicdomain/zero/1.0/" \
  --composition-rights public-domain \
  --composition-rights-basis "Composer died 1917; published 1899" \
  --redistribution permitted \
  --verified-by "curation pass 1"
```

Two rights questions are recorded separately because conflating them is how a
library ends up redistributing something it may not. A Joplin rag is a
public-domain **composition**; a particular MIDI sequencing of it made in 2003 is
a separate copyrightable **work** whose author may reserve every right. Both must
clear before the file is redistributable.

`--license` takes an established license id rather than free text, because
free text cannot be checked. A string like `Free for personal use` — the
characteristic MIDI-archive grant — is refused, not because it is known to be
restrictive but because it is unestablished, and the audit never reads absence
of evidence as permission. Establishing a new license means adding it to the
table in `openorchestrion.library.rights` after actually reviewing it.

### Importing a curated set

For a curated collection — where every file has its own source, license and
composer — evidence goes in a manifest, one row per file:

```bash
openorchestrion-import-midi --from-csv candidates.csv --library-root var/library
```

Columns are `path`, an optional `sha256`, and the evidence fields. Each row is
audited independently: a row that does not hold up is reported with its manifest
line number and skipped rather than costing the rest of the run, and the command
exits non-zero so a scripted run does not look successful because most rows
parsed. An unknown column is refused outright and lists the valid ones — a
misspelled `attribution` would otherwise be silently dropped, which means
shipping a file without the credit its license requires.

Where `sha256` is given, the file is checked against it before import. The
person who read the license and the machine that imports the bytes are usually
not the same, so this is what ties a researched claim to specific bytes; a
mismatch is refused as a rights failure, since different bytes may be a
different arrangement under different terms.

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

OpenOrchestrion never upgrades an unknown/personal file to redistributable merely because it imported successfully. `verified-open` is an explicit provenance assertion, and it is refused unless the recorded evidence supports it:

- `source_reference`, so the claim can be re-checked against where the file came from;
- `composition_rights` established as public-domain or licensed, with a stated basis when public-domain — a bare "public domain" is an opinion, and the basis is what makes it reviewable by someone who was not there;
- `license`, an established id for the MIDI file or arrangement itself;
- `redistribution` consistent with that license, and attribution text recorded whenever the license obliges us to credit someone.

A refused claim fails the whole import rather than writing a weaker one, so a
partially-evidenced library is never produced by accident. `personal` and
`unknown` assert nothing about redistribution and therefore carry no research
burden, which is the right default for a user's own collection.

If a content-addressed asset already has a sidecar, re-import does not silently overwrite its rights metadata. Rights research genuinely arrives after the bytes do, so revising a claim is a first-class operation with its own command:

```bash
openorchestrion-rights <asset-id> \
  --library-root var/library \
  --rights-status verified-open \
  --source-reference "https://example.org/piece-record" \
  --license CC0-1.0 \
  --composition-rights public-domain \
  --composition-rights-basis "Composer died 1917; published 1899" \
  --redistribution permitted \
  --verified-by "curation pass 1"
```

This writes the sidecar **and reconciles the catalog** in one step. That matters
because `rights_status` gates what a station may play: a sidecar saying
`verified-open` while `catalog.db` still says `personal` means the research had
no effect on what the appliance actually plays, and nothing would say so. Pass
`--no-reindex` only for scripted bulk runs that reindex once at the end.

Only the fields you pass are changed — omitting a flag leaves stored evidence
alone rather than resetting it to `unknown`. `--show` prints the current record,
and `--expect-revision` refuses the write if the sidecar moved underneath you.
The underlying `set_rights()` remains available for programmatic use.

`provenance` remains a protected block that ordinary curation cannot touch, and
`set_rights` goes through the same advisory lock, atomic write and revision
check as every other sidecar edit. The audit runs against the **merged** result,
so a claim cannot be raised to `verified-open` by an edit that leaves the
supporting evidence behind. `imported_at` records when the bytes arrived and is
not editable; withdrawing a claim back to `personal` never requires evidence,
since only asserting one does.

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
