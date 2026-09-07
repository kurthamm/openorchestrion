# Autonomous listening-library admission

The owner prefers a substantial, varied collection of good MIDI performances over
an unfiltered import count. Admission is decided automatically per file, not by
source collection or a target library size. It is not a claim of human audition.

## Policy: household-listening-v1

The scanner verifies each MIDI digest and sidecar identity and reads the raw timed
event stream. It preserves source bytes, metadata, and distinct performances.
The following material is archived outside normal browsing and station selection:

| Reason | Rule |
|---|---|
| Unreadable/identity mismatch | Source cannot be inspected or identities disagree. |
| Unsupported asynchronous MIDI | SMF type 2 has no supported common playback timeline. |
| No musical notes | No positive-velocity note-on events. |
| Invalid time signature/duration | Nonpositive numerator or invalid timeline. |
| Extreme event gap | An event gap exceeds 120 seconds. |
| Excessive nonmusical tail | End time exceeds the last note/controller/expression event by more than both 30 seconds and 20% of duration. |
| Short-form or sparse content | Last note event is before 30 seconds, or fewer than 64 note attacks. |
| Mechanical piano performance | All observed pitched programs are piano-family, no drums or nonzero note banks, at least 95% of attacks have one velocity, no changing expressive/pedal controllers, and no tempo development after time zero. |
| Duplicate timed playback | Same complete, microsecond-normalized playback event fingerprint, including instrument/controller events and completion time. |

The short-form and flat-piano rules are household listening preferences, not proof
that those files are defective or artistically worthless. They can exclude a
legitimate short piece or a deliberately mechanical piano arrangement. That tradeoff
is explicit and reversible. Organ and ensemble music are not subjected to the
flat-piano rule. Missing composer, no Program Changes, few tracks, source reputation,
file size, and source-assigned A/B/C grades do not by themselves reject a file.

Distinct expressive performances and arrangements are retained. Same-title works
are never merged by this process. One deterministic representative is kept only
when the actual timed playback fingerprint is identical. This does not attempt to
rank loosely similar performances or judge the artistry of a composition.

## Publication and recovery

`openorchestrion-curate --library-root ROOT --output PLAN.json --workers 2` creates
a plan without changing the collection. The plan records every asset, source,
title, input revision, measured facts, admission reasons, and duplicate survivor.

With playback and all library writers stopped, publish using:

```
openorchestrion-curate --library-root ROOT --apply-plan PLAN.json
```

Publication first verifies that every input and the complete inventory still match
the scan. It saves the plan, prior admission policy, and SQLite backup beneath
`ROOT/archive/RUN/`, moves excluded MIDI/JSON pairs into that run's `assets/`
directory, publishes `ROOT/listening-admission.json`, and atomically rebuilds the
active catalog. Exceptions trigger file/policy/catalog restoration. The run's
state file records publication or restoration. No MIDI or metadata object is
deleted or rewritten. Keep this archive in appliance backups.

For the latest unchanged run, with playback and writers stopped:

```
openorchestrion-curate --library-root ROOT --restore-run ROOT/archive/RUN
```

Restore refuses an older run or later active-library/metadata changes instead of
overwriting them. A process/power failure can leave the durable prepared run and
lock for administrator recovery; exception rollback is tested, but power-loss
recovery is not a transactional filesystem guarantee. Do not remove that run or
lock without inspecting its state and original/archived pairs.

## Future imports

Once the admission manifest exists, both full rebuilds and single-asset indexing
exclude unadmitted imports. Re-run the automatic scan and publication to admit
new qualifying music; there is no required human per-file review. Importing or
reindexing alone must not bypass the listening policy. Archived files remain
outside the active `assets/` directory.

## Playback correction

Automatic voicing now skips channels with multiple source patch/bank states or
nonzero bank selections. It no longer replaces an entire changing channel with
one inferred patch. Explicit user-selected instrument overrides remain supported.
Original source files are unchanged. This safeguard does not claim complete
device-specific bank/SysEx fidelity or audition on an unavailable keyboard.

## Validation

Regression coverage includes good expressive piano, flat piano exclusion, organ
preservation, extreme tails, duplicate playback with different titles, stale-plan
rejection, new-import gating, successful restore, and an injected failure between
the two moves of a MIDI/JSON pair. Offline scanner results are compared with the
Mido implementation; playback continues to use the existing Mido timeline loader.

The full Python suite passed 656 tests, followed by the added parser-fallback
regression (nine curation tests passed). Ruff, repository contracts, and an
isolated installed-wheel virtual-server/selection/queue/smoke test passed. On 182
real library files, both offline readers made the same admission decisions. Nine
cases differed in timing/fingerprint details, chiefly event-gap representation;
none changed admission. The fast reader falls back to Mido on unsupported
encodings. This rescued one valid BitMidi file with noncanonical meter encoding.

## Published collection: September 7, 2026

All 25,893 active MIDI/sidecar pairs were inspected. The final collection admits
**20,549 files** and preserves **5,344 files** in the quality archive. There was no
target count or source-wide purge.

| Source | Active | Archived |
|---|---:|---:|
| BitMidi | 16,481 | 3,106 |
| Mutopia | 2,791 | 2,238 |
| MAESTRO | 1,276 | 0 |
| Wikimedia | 1 | 0 |

Exclusion reasons overlap: 3,707 mechanical-piano, 2,699 short/sparse, 292 excessive
tails, 256 extreme gaps, 28 no-note files, one invalid meter, one unsupported type-2
file, and 69 redundant timed-playback copies. These figures must not be summed to
obtain the unique archived count. The plan records exact reasons for every file.

The published run is
`/var/lib/openorchestrion/library/archive/20260907T152511.955289Z`.
It contains the complete decision plan, unchanged excluded MIDI/JSON pairs,
original catalog backup, and publication state. The active manifest is
`/var/lib/openorchestrion/library/listening-admission.json`.

The package was installed with production dependency changes disabled. Backend
and discovery services restarted successfully; the service-account smoke check
and a three-piece station preview passed. The API reports 20,549 active assets
and 19,688 currently derived composition groups. Those groups are not a new
certification of work identity. No physical output was connected and no audition
was claimed.

Published wheel SHA-256:
`425979ce78b4325b523d6ff58a336b75aaabb12071264c84a44c92fe30d081e7`.
Decision-plan SHA-256:
`e40ab6ada55d5100cd6a70572534a2218b289074db1ce4f08515bcad9c75ba50`.
