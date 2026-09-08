# Current developer handoff — 7 September 2026

## Start from main

The primary checkout is `/home/kurt/openorchestrion` on the Pi. Use **`main`** and
create an isolated branch/worktree from current `origin/main`. Production executes a
non-editable wheel in `/opt/openorchestrion/venv`; changing a checkout does not deploy it.
[PR #94](https://github.com/kurthamm/openorchestrion/pull/94) is the integrated baseline
for acquisition, player operations, library quality and the listening-room UI.
The repository-maintenance release builds on it; its exact validation and deployment
identity are in [the maintenance record](repository-maintenance.md).

The subsequent [title metadata repair](title-metadata-repair.md) is deployed with
110 runtime files. It corrects 2,230 titles without changing the 5,861-song inventory,
preserves original labels, and distinguishes upload context from creator credits.
Use the shared identity normalizer for imports; do not reintroduce filename-prefix
composer/artist inference. The repair record documents evidence, the installed
wheel, private rollback plan and verification.

## Current product and data

The numbered [0.1.0 release](releases/0.1.0.md) adds guided **Add music** acquisition.
[Release publication/upgrades](releases.md) and [job lifecycle/locking](guided-acquisition.md)
are the current shipping contracts. Stop older acquisition workers before upgrading.

- Music-first UI: Discover, filtered library, Favorites, Queue, Recently Played,
  performance details, and Playback & devices. The current browser has no AI panel.
- Saved playlists/stations, queue editing, repeat/shuffle/continuous playback, seek,
  sleep/stop-after-song, restart persistence, previous/replay, undo, per-song settings,
  MIDI test note and system-health reporting are implemented.
- The original v2 curation retained **5,832 of 25,893 originals** and archived 20,061.
  The first nightly-acquisition run added 29; **5,861 available on September 7** is a
  dated snapshot, not a fixed capacity or promise about future daily counts.
- Admission uses `library/listening-admission.json` and `quality.sqlite3`; inspect the
  source/structural evidence rather than interpreting catalog labels as guarantees.
- Nightly acquisition runs at 04:30–04:45 America/New_York. Five reviewed sources
  feed the same quality gate. `library/acquisition.sqlite3` preserves accepted and
  rejected identities, exact-playback fingerprints, decisions, cursors and reports.
- Off-site backup is scheduled separately; normal backups include the active library,
  quality/admission state, acquisition history, playback state and listening history.
  Preserve the separate original-library archive as well. Provider credentials and
  system configuration do not silently enter the application-data backup.
- Cloudflare remote access remains protected by its existing Access configuration.
  The public project site under `site/` is separate from the protected Pi control UI.

## Development and deployment rules

Use a private copied library and injected `VirtualMidiOutput` for mutation tests.
Do not clear a user's queue, rewrite descriptive metadata, or bypass admission to test
an interface. The files' instrument programs/banks/controllers matter to playback;
metadata enrichment must not rewrite immutable MIDI bytes.

Before an update, check active playback, saved session/collections and library writers.
Retain an exact rollback wheel. Pause acquisition for a full curation or restore.
Backup/acquisition snapshots use a shared lock; retry an overlapping operation.
Install the tested wheel and verify app/discovery/tunnel state and data preservation.

```sh
python3 scripts/verify-deployed-source.py \
  --installed /opt/openorchestrion/venv/lib/python3.13/site-packages/openorchestrion
pytest -q
ruff check --select E4,E7,E9,F .
python .github/scripts/validate_repo.py
node .github/scripts/test-web.mjs
```

The source check compares all packaged runtime files, including packaged UI/unit files.
CI covers Python 3.11–3.13, browser state behavior, schema/rights contracts and a
non-editable wheel boot. Test counts and wheel hashes belong in release evidence;
older release documents are historical, not the current deployment checklist.

## Remaining work and owner constraints

[Next steps](next-steps.md) gives the current disposition of every open issue.
AI UI work, CT-X700/new-keyboard implementation and physical two-engine testing are
**deferred by the owner**. Do not infer delivery dates from old issue text.
The WK-220 checklist and 120-minute headless evidence are recorded; missing acoustic,
physical touchscreen, second-engine and enclosure evidence must remain explicitly pending.
No unmeasured hardware configuration should be promoted to fully project-validated.

## Evidence navigation

- [Current repository maintenance](repository-maintenance.md)
- [Automatic acquisition and recovery](automatic-acquisition.md)
- [Complete-listening-v2 quality publication](library-quality-publication.md)
- [Historical playback readiness](library-playback-readiness.md)
- [Historical single-keyboard endurance](single-keyboard-release-2026-09.md)
- [Historical Pi defect review](implementation-review.md)
- [Current issue dispositions](next-steps.md)
