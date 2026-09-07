# Library playback readiness — 7 September 2026

The performance panel now answers **What will play** using the same automatic
voicing or explicit rendering policy as a new queue request. Opening it does not
change the queue or send MIDI. The source instrument table remains available in
a disclosure, so the requested sounds and original file evidence are distinct.

## Data and interpretation

The scanner identifies sounding MIDI channels, their note-bearing source tracks,
programs/banks actually used by notes, default instruments before program changes,
percussion, note/velocity ranges, sustain, pitch bend and peak note demand. State
is shared across tracks on the same channel. Bank selection is latched at program
change. Controller-only tracks are not presented as extra musical parts.

Piano Only removes percussion and recomputes the overall estimate without that
channel. Explicit overrides and automatic voicing replace the displayed programs
exactly as they do in the renderer. This is a preview for the next addition, not a
readback of the policy on an already queued item or a measurement of acoustic output.

Structural warnings are not musical-quality scores. Solo piano is not rejected
for using few channels or lacking percussion. Missing sustain/dynamics are shown
as facts, not automatic rejection rules. Nonzero banks and non-default drum kits
are **unverified mappings**, not assertions that the keyboard cannot play them.
The WK-220's 48/24 limits are explicitly a reference check, not model detection or
profile binding. See the [hardware guide](hardware/casio-wk-220.md).

Peak estimates include sustained pitches, count repeated pitches once per channel,
and exclude release tails/sample layers. They cannot predict exact oscillator
usage or guarantee audible completeness. No new admission decisions are made.

## Full admitted-library audit

All **20,549 admitted files** were hashed and indexed into **127,504 sounding
channels**. All original MIDI objects and the existing 5,344 archived exclusions
remain preserved. Source-arrangement findings overlap:

| Finding | Files |
| --- | ---: |
| Estimated peak above 48 notes | 120 |
| Peak above 24 and at most 48 | 2,212 |
| Non-default banks or drum kits | 4,436 |
| Notes using implicit default programs | 3,884 |
| SysEx present but blocked by playback | 7,217 |
| MULTI_INSTRUMENT label with one sounding channel | 4,343 |

The last row is a metadata/completeness clue: it can mean a reduction, sequential
instrument changes or an overly broad upstream label. It is not 4,343 proven bad
performances. The automatic preview can resolve some source sound warnings via
overrides; these counts describe originals.

Seven files exposed a Mido 1.3.x loader defect: `build_meta_message` discards the
delta time of unknown meta types. The shared loader now recovers those deltas
from the raw SMF while retaining Mido's validation. A generated regression test
puts 480 ticks on unknown type 0x53 and verifies the note release stays at 1.0 s.
All seven real cases were compared with both analysis and playback, then repaired
using `reanalyze_asset` and individual reindex. Their non-analysis sidecar fields
were compared and preserved; backup sidecars remain on the Pi. The final audit
finds **zero note-count, peak-note or duration mismatches** against the catalog.

## Disposable index and maintenance

`playback-facts.sqlite3` sits beside the catalog. It is derived data, not a new
metadata authority. Entries use asset hash, analysis version and file identity
(device/inode/size/mtime/ctime). A miss computes verified facts in the existing
selection worker process. The web request does not write the cache or originals.
Always resolve membership through the admitted catalog first.

Build or refresh after import/repair, as the library service user:

```sh
sudo -u openorchestrion /opt/openorchestrion/venv/bin/python \
  -m openorchestrion.library.readiness /var/lib/openorchestrion/library/catalog.db
```

Use `--library-root` if the catalog is outside its library directory. Runs commit
in batches, are resumable and exit nonzero if any asset fails. No music is deleted.
Increment the facts version when changing stored analysis semantics. Rebuild this
cache after restore if absent; do not replace curated sidecars with its contents.

Read-only reproduction scripts (run with the repository dependencies installed):

```sh
python scripts/audit-library-readiness.py /path/to/library/catalog.db audit.json
python scripts/benchmark-library-readiness.py /path/to/library/catalog.db timings.json
```

Build the facts index first. The audit compares stored indexed facts with the
admitted catalog and exits nonzero for missing records or metric mismatches.
The benchmark parses files into virtual dispatches and never sends hardware MIDI.

## Responsiveness

Facet results use a bounded cache invalidated by database replacement, ordinary
writes and WAL changes. Counts come from one read transaction. Accent-folded text
search caches normalized strings, keyed by their actual contents. Favorites still
invalidate immediately when their catalog update commits.

Playback no longer revalidates every field while copying already validated source
messages with `time=0`. A per-engine source cache retains at most one timeline and
100,000 events for replay/resume. File changes invalidate it. Rendering and output
dispatch are rebuilt; cached data never retains a stale device route.

Pi 5 measurements below are preparation costs with virtual outputs, not end-to-end
acoustic latency. Three samples per file; facet/search columns use four warm calls.
The first search/facet query remains cold. Raw reports accompany this document.

| Operation | Before median | After median |
| --- | ---: | ---: |
| Warm facets | 79 ms | 0.92 ms |
| Warm text search (`bach`) | 167 ms | 41.7 ms |
| Cold preparation, 3,236 notes | 223 ms | 213 ms |
| Cold preparation, 8,341 notes | 591 ms | 489 ms |
| Cold preparation, 16,116 notes | 1,147 ms | 929 ms |
| Repeat preparation, 3,236 notes | 221 ms | 96 ms |
| Repeat preparation, 8,341 notes | 597 ms | 249 ms |
| Repeat preparation, 16,116 notes | 1,105 ms | 509 ms |

These are three representative quantiles, not a promise about all files. Cold
parsing/dispatch still scales with event count and is a remaining optimization lane.

## Release and verification

Installed September 7 at 21:35 UTC. Wheel SHA-256:
`1eeb9c2a2c7d3335ea476326dd384892ced2438eb5abd8671bff1eebec96061f`.
All **91 runtime files** match the candidate source; both services and the installed
smoke check passed. The owner delegated the restored sound choice: the prepared
Healer song was restored with Automatic voicing, stopped, at the existing volume 33.

Validation: **676 Python tests**, Ruff correctness checks, repository contracts,
browser behavior tests, and a non-editable wheel running an isolated virtual server
with the new spawned preview endpoint. Visual checks covered a solo piano and an
ensemble transformed to Electric Grand Piano, at phone and desktop widths, with
no horizontal overflow or browser errors. Production state was not used for UI
mutation tests.

Evidence is in [the readiness release directory](evidence/library-readiness/2026-09-07/).
The earlier [two-hour endurance evidence](single-keyboard-release-2026-09.md) remains
historical evidence for its exact wheel; it is not relabeled as a test of this build.

Rollback wheel: `/var/tmp/openorchestrion-release-20260907/wheel/` (SHA-256
`fad8f6271da241ac715fb1b790cb1d57ac24d007dc0648e464d94b54a10df901`). Local
release records and seven sidecar backups are under
`/var/tmp/openorchestrion-readiness-release/`. Before rollback/restart preserve
transport, queue and sound choices; the old queue API does not expose saved policies.
The repaired timing facts would also need reconciliation if rolling back the loader.

CT-X700 work, two-engine orchestration, volume features and AI activation remain
deferred. Remaining library work should prioritize evidence for suspect mappings
and arrangement labels, rather than bulk import or deleting files on channel count.


### Post-deployment loaded check

At 21:38–21:39 UTC the prepared WK-220 song played while HTTP browse, facets and
readiness previews loaded repeatedly. A 60-second virtual timing case passed:
p95 interval jitter 0.672 ms, p99 0.766 ms, maximum 1.645 ms, drift −1.328 ms.
The short virtual A/B check also passed. The song was replayed briefly to exercise
the warm path, then stopped with the same queue and volume 33. No service warnings
were recorded. This is a short regression check, not another two-hour endurance
claim or a measurement of physical two-output/acoustic timing.
