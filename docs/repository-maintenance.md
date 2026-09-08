# Public repository maintenance — September 2026

This pass starts from merged PR #94 (`afbe731`) and addresses public installation,
reproducibility, repertoire, publication and stale project state.

## Software changes

- Installer prepares wheels before stopping an existing service, uses an exclusive
  install lock, validates kiosk prerequisites, retains the old environment/units,
  and restores them after install or health failure. Failure tests execute the
  actual shell script with isolated paths and simulated host services.
- A new user can initialize an empty v2 library with `openorchestrion-acquire
  --init-empty`; private reference-curation evidence is no longer a prerequisite
  for first use. Existing assets or admission decisions cannot be cleared by it.
- Root backup and unprivileged acquisition share a readable lock file; root-first
  creation under a restrictive umask no longer blocks the importer.
- ZIP inspection/staging now audits every member and requires separate archive
  and selected-file identities, bounded sizes and per-file rights.
- Two documented Donizetti derivatives deepen the public starter repertoire from
  16 to 18 files without lowering quality thresholds or inventing performance data.
  See [the repertoire review](repertoire-candidate-review.md).

## Documentation and publication

[Getting started](getting-started.md) provides clone-to-first-music instructions
and an isolated development example. [Troubleshooting](troubleshooting.md) covers
common failure states. The README, handoff, status, roadmap, hardware matrix,
reference build/BOM, white paper and static site distinguish shipped behavior,
historical measurements and deferred hardware/AI work.

GitHub Pages Actions source was enabled through the authenticated repository
settings on September 7. [PR #95](https://github.com/kurthamm/openorchestrion/pull/95)
merged as `f2b9c5466d4ae730f5efd7feee773af6b375ef1a`. All five
[GitHub CI jobs](https://github.com/kurthamm/openorchestrion/actions/runs/34177387478)
passed, including Python 3.11–3.13. The
[Pages deployment](https://github.com/kurthamm/openorchestrion/actions/runs/34177483813)
succeeded and the [public site](https://kurthamm.github.io/openorchestrion/)
was verified in Chromium. The repository About description and website link were
updated to match the current product.

## Development checkout cleanup

Nine obsolete Pi worktrees were archived and removed. Their complete file contents
(including ignored artifacts), dirty patches and all Git refs were preserved in
`/var/tmp/openorchestrion-repository-archive-20260908`. Every remaining file was
compared with its archive before removal. A root-owned artifact required repairing
ownership during cleanup; it was already captured in the verified archive.

`all-refs.bundle` SHA-256:
`e0bb031ca6068e97ced6d2ffa6231691e970e7930783725c8f758c6637c81943`.

Restore commits by cloning/fetching that Git bundle. Restore a worktree's saved
files from its named tarball into a fresh checkout, omitting the old `.git` file;
the old `.git` points to retired worktree metadata. The archive manifest records
individual tarball hashes. No music recovery archive or release rollback wheel
was deleted. Main and the active maintenance checkout remain separate.

## Validation record

The Pi suite passes **742 tests**; Ruff, schema/profile/generated-MIDI contracts,
the 18-file repository rights audit, Markdown link checks and browser state tests
pass. A non-editable wheel booted outside the checkout and passed API/queue/web
smoke checks with graceful shutdown. Real first-use commands imported/tagged all
18 starter files, then initialized a separate empty v2 library and acquired one
qualified SMD file without private reference evidence.

Installed wheel SHA-256:
`34f69e106f387aaaece2c4b41b64a0adcf4bfd48f94ca02c01d1a33e614ec512`.
All **108 runtime files** match the reviewed source. App, discovery and tunnel
are active; the 5,861-file personal library, queue, collections and saved player
session were preserved. The nightly acquisition timer remains enabled.
Exact prior-runtime rollback wheel SHA-256:
`79c78b21875e165195d4c4b163182ea2812f4446ab7f4237a037fc0554c3a0d1`.
Release wheels are retained in `/var/tmp/openorchestrion-maintenance-release/`.
The two Donizetti additions are public starter files; this maintenance deployment
does not silently re-import the starter catalog into the owner's personal library.

The Pi primary checkout is clean at merged PR #95, and the installed runtime has
108 matching source files. Issues #6, #10 and #64 are closed with linked evidence.
Issues #1, #8, #11 and #84 retain the unavailable/deferred hardware and physical
validation work; combined real-output and acoustic timing obligations are retained
explicitly in #1/#84. No physical acceptance result was inferred from virtual MIDI.
Physical touchscreen usability and acoustic latency cannot be
certified by virtual display/software timing measurements. New-keyboard and
two-engine implementation remain explicitly deferred by the owner.

## Pi-local Chromium timing evidence

On `afbe731`, Chromium 152.0.7977.82 ran the real Library UI under Xvfb at
1280×720 while the installed scheduler benchmark ran. There were 114 successful
read-only catalog requests and a connected WebSocket (one initial snapshot; playback
was stopped). The browser survived, and the queue/state were unchanged.

The 599.75-second case passed: p95 interval jitter **0.646 ms**, p99 **0.660 ms**,
maximum **1.631 ms**, drift **−0.555 ms**. The short two-virtual-output case also
passed (maximum send skew **0.062 ms**). Throttle flags were `0xe0000` before/after:
historical flags already present, no active throttle bits at those observations.

[Full timing report](evidence/maintenance/kiosk-timing.json),
[environment and workload](evidence/maintenance/kiosk-environment.json),
[worktree archive manifest](evidence/maintenance/worktree-archive.json).
This supplements the previous loaded 120-minute headless run. It is not a new
120-minute Chromium run, active physical-playback test, audio-latency measurement
or physical display/input validation.
