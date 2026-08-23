# Curating descriptive metadata

Importing a MIDI file records what can be derived from its bytes. It cannot
know that a file is *Maple Leaf Rag*, that it suits dinner, or that someone
loves it. Those judgements are curated, and this is where they are written.

Until they exist, a library is functionally invisible: Smart Stations score
against nothing and fall back to "relaxed requested metadata preferences",
browse screens show untitled assets, and favorites have nowhere to live.

```text
before tagging                          after tagging
──────────────────────────────────      ──────────────────────────────────
1. polyphony-64.mid                     1. Air on the G String | J.S. Bach
   score 0.68                              score 25.68
   "eligible library candidate"            "theme match, energy 1/5, quality A"
relaxed: relaxed requested metadata      (no relaxation)
```

## Where curated metadata lives

In the `descriptive_metadata` block of the asset's sidecar, beside the stored
MIDI object:

```text
var/library/assets/
  <sha256>.mid      the immutable, content-addressed MIDI object
  <sha256>.json     the sidecar — the durable source of truth
```

The sidecar holds three data classes that must never bleed into each other:

| Block | Who writes it | Can curation change it? |
| --- | --- | --- |
| `deterministic_analysis` | the analyzer, from the MIDI bytes | No |
| `provenance` | the importer, at ingest | No |
| `descriptive_metadata` | a person, via the tools here | Yes |
| `ai_enrichment` | a future AI pass, kept separate | No |

**Rights cannot be upgraded by a curation edit.** Marking a piece a favorite or
giving it a title never touches `rights_status`, and an edit that tries is
refused rather than silently ignored.

## Editable fields

`title`, `composition_title`, `composition_id`, `composer`, `artist`, `era`,
`year_composed`, `genres`, `moods`, `themes`, `tags`, `instrumentation`,
`performance_type`, `quality_grade`, `familiarity`, `energy`, `favorite`.

Values are **free text, normalized rather than restricted**. A hobbyist library
will always carry tags nobody anticipated, so `genres` accepts whatever a person
types; it is only trimmed, blanks are dropped, and duplicates differing solely
by case collapse onto the first spelling seen. `performance_type` and
`quality_grade` are the exceptions — they drive routing and selection, so they
are closed enumerations.

`familiarity` and `energy` accept `low`/`medium`/`high` or `1`–`5`, and are
stored as the integer so round-trips stay deterministic.

## Tagging one asset

```bash
openorchestrion-tag sha256:4b343e9c… \
  --title "Clair de Lune" --composer "Claude Debussy" \
  --genre classical --mood reflective --theme dinner \
  --performance-type SOLO_PIANO --familiarity high --energy low --favorite
```

`--show` prints the current block and its revision. `--clear FIELD` removes one.
List flags are repeatable and also accept comma-separated values.

## Tagging a collection

A CSV keyed by SHA-256, one row per asset, columns named after the fields:

```csv
sha256,title,composer,genres,themes,familiarity
sha256:4b343e9c…,Clair de Lune,Claude Debussy,"classical,impressionist",dinner,high
sha256:63c000e0…,Maple Leaf Rag,Scott Joplin,ragtime,cocktail,high
```

```bash
openorchestrion-tag --library-root var/library --from-csv tags.csv
```

**Blank cells are left alone, not cleared.** A spreadsheet exported with every
column would otherwise wipe fields the editor never filled in. Use `--clear` to
remove a value deliberately.

One bad row does not lose the others: failures are reported per asset and the
command exits non-zero so a scripted run cannot look successful.

## Editing semantics

**Merge, not replace.** An edit updates the fields it names and leaves the rest
alone.

**Validate first, write once.** The entire change set is checked before anything
is written, so a single bad field cannot leave a half-applied edit — and an
invalid edit always leaves the previous valid sidecar exactly as it was.

**Atomic writes.** The new sidecar is written to a temporary file beside the
target, flushed and fsynced, then moved into place with `os.replace`. An
interrupted edit or a power loss cannot leave a truncated sidecar behind.

**Optimistic concurrency.** Every read returns a `revision` — a digest of the
sidecar's bytes. Pass it back as `--expect-revision` (or `expected_revision=`)
and the write is refused if the sidecar moved underneath you, so two editors
cannot silently overwrite each other:

```bash
$ openorchestrion-tag <asset> --show
sha256:4b343e9c…  revision 91c2f0ab77d1

$ openorchestrion-tag <asset> --title "New" --expect-revision 91c2f0ab77d1…
error: sha256:4b343e9c… was modified by someone else
       (expected revision 91c2f0ab77d1, found 4d81aa30bc95)
```

Omitting the revision forces the write. That is the right default for a single
person at a kiosk and the wrong one for two admin browsers, so the API passes it.

## Catalog reconciliation

After a successful edit the asset's rows in `catalog.db` are refreshed from the
sidecar, in one transaction, so browse and stations reflect the change at once.

This is a convenience, never a source of truth. `catalog.db` remains fully
rebuildable: delete it, run `openorchestrion-reindex`, and every curated value
returns from the sidecars. `--no-reindex` skips it when bulk-tagging ahead of a
single full rebuild.

## Backup implications

See [Backup and recovery](backup-recovery.md) for the full model. In short:

- **`assets/*.json` sidecars are irreplaceable** and must be backed up. Curated
  metadata is human judgement; nothing can reconstruct it from the MIDI bytes.
- **`catalog.db` is disposable** and need not be backed up, though it is small
  enough that including it costs nothing.
- **`history.db` is irreplaceable** for a different reason — it records what was
  actually played.

A restored library is `assets/` plus `history.db`; the catalog rebuilds itself.

## Programmatic use

```python
from openorchestrion.library import read_metadata, update_metadata, set_favorite

record = read_metadata("var/library", asset_id)
update_metadata(
    "var/library", asset_id,
    {"title": "Clair de Lune", "genres": ["classical"]},
    expected_revision=record.revision,
)
```

`set_favorite()` is the narrow case behind
`POST /api/library/assets/{asset_id}/favorite`.
