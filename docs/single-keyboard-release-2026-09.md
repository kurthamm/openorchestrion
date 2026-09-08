# Single-keyboard release — 7 September 2026

> Historical release/audit evidence: library counts, service state and build hashes
> below describe this report's original measurement. For the current release and
> count baseline, see [project status](../PROJECT_STATUS.md) and
> [repository maintenance](repository-maintenance.md). Do not restore an older
> admission manifest or deployed build from this report as if it were current.

## Shared implementation and deployment

[PR #85](https://github.com/kurthamm/openorchestrion/pull/85) merged the deployed reliability fixes, curated listening library and listening-room redesign into `main` at `cff40bf5693078133dc7ed5453d00978a5baaaa5`. Main's independent acquisition tools and future two-engine plan were preserved. Duplicate facet endpoint and obsolete frontend wiring conflicts were resolved in favor of the deployed asynchronous API and redesigned shell. Developer context now records the admission policy and deferred AI/new-keyboard work.

The primary Pi checkout `/home/kurt/openorchestrion` follows main. Production runs a non-editable wheel, not that checkout:

- Wheel: `openorchestrion-0.1.0.dev0-py3-none-any.whl`
- SHA-256: `fad8f6271da241ac715fb1b790cb1d57ac24d007dc0648e464d94b54a10df901`
- Retained candidate: `/var/tmp/openorchestrion-release-20260907/wheel/`
- Source tree: `49c336212733d6f4e82b5be01e9728fd6eae7714`
- Previous wheel: `94e08cc804dcd5e2efb85f4fb294670d9476c482ba25d214ec5125e7cd328bca`, retained at `/tmp/openorchestrion-listening-release/new/`.

The only runtime difference from the previous wheel is `playback/benchmark.py`, a separate command-line harness. The server's playback engine, API and browser files are unchanged. This allowed installation without restarting the application: service PID 45816 and restart count zero were unchanged, and the prepared queue was preserved. Afterwards, `scripts/verify-deployed-source.py` verified all **88 runtime files** against main with no differences.

## Validation and repaired defects

- **665 Python tests passed on the Pi**, including five new capture regression cases.
- Ruff correctness checks and repository contracts passed.
- [CI run 134](https://github.com/kurthamm/openorchestrion/actions/runs/34148401219) passed the Python 3.11, 3.12 and 3.13 jobs, browser-state tests, lint, repository contracts and non-editable wheel smoke test.
- Production `openorchestrion-smoke` passed.

The first CI attempt failed during the Python 3.13 dependency build because ALSA development headers were missing. CI now installs `libasound2-dev` before installing test dependencies; the actual failed job is retained in [run 133](https://github.com/kurthamm/openorchestrion/actions/runs/34148127805).

The first three Pi timing reports were **invalid measurements**. The collector took the first N outgoing messages, but the engine now sends GM channel resets and program initialization before musical notes. Consequently it reported almost the entire short fixture as negative drift. The correction measures Note On/Off events, verifies exact note count and ordered type/channel/pitch identity, and excludes reset/Panic controllers. It does not change the scheduler or relax any timing target. Tests cover real router initialization/cleanup, missing/extra/wrong notes, and a complete engine playback lifecycle.

## Timing evidence

The [raw JSON and environment evidence](evidence/pi-timing/2026-09-07/) retains original invalid runs as well as corrected results. Raw benchmark reports are unedited. The published environment copy omits private IP addresses and identifies Wi-Fi as the active network. Complete local observations remain under `/var/tmp/openorchestrion-release-20260907/`.

The reference here is a Pi 5 with four Cortex-A76 cores, Debian 13, Python 3.13.5, microSD storage, the `ondemand` governor, and a directly attached CASIO USB-MIDI endpoint. WK-220 model identity follows the owner and earlier issue #1 evidence, not inference from the generic USB name. The power supply was not externally verified. There is no local Chromium kiosk.

Three corrected `headless-idle` short runs passed. Three authorized `headless-active-one-output` short runs also passed. The loaded variant replays the existing prepared track through the server-owned physical MIDI output, keeps a WebSocket connected, and issues ordinary browse, search, facets and history reads over loopback approximately every 12 seconds. It preserves the queue, rendering policy and user-set volume. This is a headless workload, not a kiosk measurement.

Two preliminary loaded attempts were invalidated by a bug in the external test monitor: it treated volume-command playback snapshots as transport interruptions. Service access logs confirmed `/api/volume` requests, not a deliberate stop. The monitor then ceased repeating the track, and the owner reported silence when it ended. The monitor was corrected to permit continuing playback and volume changes while still relinquishing control on a user pause/stop or queue replacement. These attempt records are retained as test-harness interruptions, not scheduler failures or completed endurance runs. The owner explicitly authorized the uninterrupted keyboard test.

**The headless single-keyboard endurance run passed every provisional software target.** The authorized run, including three short checks, lasted from 17:55:33 to 19:56:23 UTC on September 7. The long case ran for 7,200.704 seconds of wall time against 7,199.750 seconds of musical time, capturing all 28,800 expected notes. Its JSON and all three short reports have `passed: true`; each command exited zero.

| Long-case metric | Measured | Limit |
| --- | ---: | ---: |
| p95 absolute interval jitter | 0.674 ms | 2 ms |
| p99 absolute interval jitter | 0.693 ms | 5 ms |
| Maximum absolute interval jitter | 3.653 ms | 10 ms |
| End-to-end drift | -3.815 ms | ±5 ms |
| Included short-case virtual A/B p95 skew | 0.043 ms | 1 ms |
| Included short-case virtual A/B maximum skew | 0.050 ms | 3 ms |

The WK-220 remained connected across 22 playback starts (21 complete track transitions and the final partial play). The runner received 2,450 WebSocket messages and completed 859 HTTP requests without a request exception or application error event. The 239 periodic environment samples all retained PID 45816, restart count zero and active service state. Temperature ranged from 47.2 to 53.2°C. Historical throttle flags were already `0xe0000` before testing and stayed unchanged; no sampled current undervoltage/throttling flags were set. Post-run smoke and 88-file deployed-source verification passed. The service journal had no warning-or-higher entries in the run window.

HTTP p95 was 256 ms and p99 874 ms overall. The maximum, 2.334 seconds, was a playback-start request; ordinary first-page browsing peaked at 5.986 ms, text search at 286 ms, and browse-facet loading at 992 ms. These are observed latencies, not new acceptance thresholds. Startup/facet responsiveness can be optimized separately; the current scheduler targets all passed under this workload.

The external runner polls every three seconds and explicitly replays after each completion, so this is sustained repeated playback rather than gapless playback. Observed between-track gaps had a median of 1.003 seconds and maximum of 4.164 seconds. The [observation summary](evidence/pi-timing/2026-09-07/loaded-observation-summary.json) records the percentile method, per-endpoint numbers and SHA-256 of the complete local JSONL. No acoustic continuity is inferred from these software events.

After finishing, the runner stopped playback and left the original one-item queue prepared, with volume 33 unchanged. A fresh WebSocket snapshot at 19:58 UTC confirmed stopped state, the same asset, and a ready CASIO output. The `playback` field in the runner's result is its last pre-cleanup snapshot; it is not a claim that music was still playing after cleanup.

## Scope and remaining limits

For unattended WK-220 playback, use the [documented TONE + POWER startup procedure](hardware/casio-wk-220.md) to disable Auto Power Off. The owner reported shutdown during long pauses and confirmed performing this physical startup procedure before the final run. This is operator confirmation, not remote readback of a keyboard setting. The preceding run was explicitly terminated and retained as a setup interruption so the final acceptance covers a fresh full two hours.

The active library remains 20,549 admitted performances with 5,344 exclusions archived and all 25,893 originals preserved. This release does not import or recurate music.

The virtual benchmark measures software note scheduling and virtual send skew. Physical MIDI processing is background load through the real server, but neither these JSON reports nor USB subscription state measure acoustic latency, timbre or audible musical completeness. Earlier WK-220 listening checks remain separate historical evidence.

Issue #6 remains open for any outstanding acceptance profiles and hardware evidence. Local Chromium kiosk load, physical two-output timing, CT-X700 validation and AI activation are deferred. No volume-control feature was changed.
