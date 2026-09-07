# Complete listening library, policy v2

## Result and scope

The 7 September 2026 assessment covers all **25,893 original MIDI files**, including
the previous archive. It qualifies **5,832**: 4,160 BitMidi arrangements, 1,276
MAESTRO performances and 396 Mutopia exports. It recovers 129 previous exclusions.
The remaining **20,061** originals are retained in the archive: 19,522 have
unresolved quality/completeness evidence and 539 are excluded by specific findings.
Unresolved does not mean proven bad. There is no admission quota and no user
audition queue. Original MIDI and sidecar bytes are unchanged.

See [decision summary](evidence/quality-final/summary.json) and the complete
[compressed per-file decisions](evidence/quality-final/decisions.json.gz).
The [deployment record](evidence/quality-final/deployment.json) verifies the live
5,832-file catalog, all original hashes and preserved saved collections. The
installed wheel SHA-256 is `a616f1471d137e8e3250d0d917eb05d8551ffb0f550e4b80374abfa693e6a9d5`;
98 runtime files match the reviewed source. All 704 tests, contracts, Ruff, browser
state checks and the isolated installed-wheel smoke passed. The preceding 1,672-file publisher-only candidate was never published.

## What admission means

Admission requires a parseable, hash-verified file, positive evidence for a
self-contained arrangement, and meaningful encoded performance detail. It is an
automated, conservative listening selection, not an acoustic audition or a claim
that every rendition contains every note of the original composition.

Two evidence classes are deliberately visible in the performance-details UI:

* **Publisher verified:** exact MIDI bytes matched to the checksum-verified MAESTRO
  v3 MIDI release, or an exact Mutopia published export compared with its RDF
  instrumentation and other MIDI members. Named individual ensemble parts remain
  excluded. A source label alone never qualifies a file.
* **Structurally assessed:** MIDI evidence supports a self-contained rendition,
  independently of publisher certification. Substantial piano writing must combine
  chords, broad registers, articulation and coverage across the piece. Ensembles
  need distinct sustained melody, bass and chordal accompaniment roles. This is an
  inference, and cannot override evidence that the file is an individual part.

Structural inference requires at least 90 seconds and 300 attacks. Piano evidence
requires an explicitly selected GM piano, at least 500 attacks, 24 pitches, 20%
shared-onset attacks, broad registers in nine of twelve time sections, activity in
eleven sections and eight note-duration values. Ensemble roles require eight active
sections, explicit GM assignments, register/pitch variety and suitable chord or
melody behavior. Excessive muted or zero-duration notes prevent this inference.
These thresholds express this collection's listening preference; shorter valid
works and unconventional arrangements may remain unresolved. See
`library/quality_structure.py` for the exact reproducible rules.

Expression requires verified performance capture or at least half the pitched
attacks in substantial parts with meaningful velocity variety or changing
expressive/pedal controllers. Constant initialization messages do not count.
This can conservatively omit legitimate unvarying organ/score exports; it does not
label them corrupt or artistically worthless. Rubato does not require tempo-map
changes. Missing lyrics, composer or pedal events alone do not fail a file.

Unreleased pitched keys, unexplained silence/tails exceeding both 20 seconds and
15% of duration, unsupported/corrupt streams, and contradictory published
instrumentation prevent admission. Percussion-only material is outside this
full-song library. Only identical timed-playback fingerprints are deduplicated;
same-title performances remain separate. The accompanying same-title inventory is
for developer inspection, not an automatic ranking of versions.

## Quality versus keyboard realization

Admission assesses the source arrangement. It does not promise equal fidelity on
different keyboards. Nonzero sound banks, unusual drum kits, unverified device
setup and estimated WK-220 voice-capacity pressure remain compatibility warnings.
They do not automatically erase a musically useful source. The What will play
panel separately shows requested/rendered instruments and current sound-policy
effects. The new evidence panel shows per-channel velocity diversity and changing
versus constant sustain, sostenuto, soft pedal, expression and other controls.

This implements the separation defined in [the quality standard](library-quality-standard.md).
Unresolved essential device mappings still prevent a claim of faithful hardware
realization, even when the source is admitted. No new keyboard or acoustic fidelity
certification is claimed. SysEx remains blocked by the existing player.

## Reproduce assessment

Copy a quiescent library snapshot including `assets/`, `archive/*/assets/` and
`listening-admission.json`. Retain exact sidecars. Windows copied the 334,086,486-byte
compressed snapshot in 45.67 seconds; total transfer/extraction took 248.64 seconds.
The four-process primary scan took 598.2 seconds. The supplementary structure and
publisher checks are additional work, not included in that scan time.

```sh
python -m openorchestrion.library.quality ROOT facts.jsonl --workers 4
python -m openorchestrion.library.quality_structure ROOT facts.jsonl structure.jsonl
python scripts/verify-maestro-source.py source-evidence
python scripts/verify-mutopia-sources.py ROOT source-evidence
python -m openorchestrion.library.quality_plan ROOT \
  --facts facts.jsonl --structure structure.jsonl \
  --evidence source-evidence/maestro-evidence.json source-evidence/mutopia-evidence.json \
  --output decisions.json
```

The verifier scripts fetch only referenced publisher resources and cache evidence.
Some Mutopia resources were unavailable: 26 source-verification errors remained;
absence of verification never becomes publisher approval. Input SHA-256 values and
individual source/member hashes are retained in the decision artifacts. No MIDI,
lyric payload or publisher archive is committed to GitHub.

## Publish, restore and future imports

Stop playback and all library/catalog writers before either operation. The
transaction checks the full inventory and every MIDI and sidecar hash before
moving anything. It rejects stale scans and destination collisions. It backs up
the admission manifest and databases, journals the plan, moves each pair, creates
`quality.sqlite3`, writes the v2 allowlist and rebuilds the catalog. Ordinary
exceptions roll back moved files and databases; the filesystem operation is not
a single atomic rename of the whole collection.

```sh
python -m openorchestrion.library.quality_plan ROOT --apply decisions.json
python -m openorchestrion.library.quality_plan ROOT --restore ROOT/archive/quality-RUN
```

Restore verifies the current publication's inventory and hashes first. Do not
restore an old run over later imports or metadata edits. After a power loss with a
`prepared` journal, keep writers stopped and reconcile the journal's original and
destination pairs before resuming; do not simply remove the lock and restart.
`restore_files` is the internal rollback primitive for a verified interrupted run.

The v2 manifest is authoritative for both catalog rebuild and individual reindex.
New imports remain outside the admitted catalog until assessed and included by a
new whole-inventory plan. The old v1 publisher refuses to overwrite v2. Do not
remove the allowlist as an import workaround.

Normal application backup now preserves the active library's admission manifest
and quality database, alongside the existing history, saved collections and player
session. **It does not include the quarantine archive.** Preserve the separate full
library snapshot and the complete on-device archive for recovery of rejected or
unresolved originals. Retention must cover originals and evidence, not just the
active-library ZIP.

All six durable player workflows and Cloudflare access security remain in the
release baseline. Saved collections are preserved. An archived item referenced by
a saved playlist may be unavailable; retain its identity rather than silently
rewriting the playlist. The deployment record states any necessary active-queue
adjustment. No AI interface is added.

The owner explicitly requested removal of the queued Mercury blues rendition.
It was removed before the restart; its completeness evidence was unresolved. The
queue is empty, playback stopped, and repeat/shuffle/continuous settings and saved
collections were preserved. Both application and discovery services are active.
