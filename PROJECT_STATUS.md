# Project Status

## Phase

**Appliance-ready software / physical hardware proof**

OpenOrchestrion now has the complete local-first software path from MIDI ingestion and curated metadata through Smart Station/Concierge selection, server-owned queue/playback, synchronized multi-device routing, responsive household/kiosk UI, durable history, CI, and reproducible Raspberry Pi appliance packaging.

The software can be installed from a wheel or checkout, boot under systemd with zero MIDI hardware attached, serve the packaged UI, and run in either headless or Chromium-kiosk mode. The next architectural evidence is physical: real Pi 5 timing under appliance load and end-to-end MIDI/audio validation on the target sound engines.

## Current hardware targets

The intended first two-engine build is:

1. **Casio CTK-6200** — primary/general ensemble engine.
2. **Yamaha PSR-EW300** — complementary Yamaha sound engine.

Both are documented MIDI-receiving candidates with nominal 48-note polyphony and broad sound sets. Acquisition and physical project validation are still pending. The earlier Casio CT-X700 remains a documented-compatible fallback/reference and has its own hardware-proof issue.

## Implemented software foundation

### Synthetic MIDI conformance and timing harness

The generated suite covers single notes, velocity, sustain, Program Change/Bank Select, GM ensemble/percussion, receive range, 16/32/48/64-note stress, two-piano split, synchronization clicks, endurance, and parser resilience.

The playback benchmark measures real `SystemClock` scheduler jitter, long-run drift, relative timing error, and simultaneous two-output skew. The harness is implemented; Issue #6 remains open for the reference Pi 5 run under actual appliance load and later MIDI-to-audio measurements.

### Deterministic MIDI analyzer and robust importer

Provides SHA-256 identity, timing/tempo, tracks/channels, programs/banks, controllers, sustain, percussion, note/velocity statistics, expressive-event/SysEx reporting, and estimated peak simultaneous sounding notes.

The importer isolates malformed/truncated/oversized files instead of losing the remainder of a batch. `peak_simultaneous_notes` now models one sounding voice per `(channel, note)`, including sustain and channel-mode controller semantics, and `openorchestrion-reanalyze` repairs existing sidecars without re-importing content.

### Durable sidecars and curated metadata

Content-addressed MIDI objects and JSON sidecars are authoritative. Curated `descriptive_metadata` is editable through `openorchestrion-tag` or SHA-256-keyed CSV bulk edits, with free-text normalization for descriptive facets and stable enums where behavior depends on them.

Writes are atomic, guarded by optimistic revisions plus per-asset writer locking, preserve provenance/rights and AI enrichment, and reconcile the rebuildable catalog. Favorites persist through the real API. Corrected analyzer facts can be re-derived while curated metadata remains intact.

### Rebuildable SQLite catalog

`catalog.db` rebuilds from sidecars and indexes compositions separately from MIDI performances, including curated metadata, provenance, rights, and compatibility-relevant analysis. Per-asset reconciliation removes orphaned composition rows correctly. The catalog is disposable; sidecars are not.

### Deterministic Smart Stations

Validated `PlaybackIntent` produces explainable queues with exact/partial/fallback matching, weighted preferences, hard exclusions, composer diversity, duration targets, device/MIDI limits, seeded variation, favorites, quality, no-repeat inputs, and explicit relaxation diagnostics.

### Durable play history

`history.db` is separate from the rebuildable catalog. It records queued, started, substantially played, completed, skipped, and failed attempts and feeds no-repeat/staleness behavior back into station selection. Normal service shutdown stops active playback so history attempts are not stranded.

### AI Music Concierge

Provider-neutral natural-language interpretation produces strictly validated `PlaybackIntent`, preserves hard constraints during refinement, supports bounded conversational sessions, and falls back to deterministic offline interpretation. AI never receives direct MIDI/playback control.

A concrete hosted/local provider adapter remains optional future work; it is not required for offline appliance operation.

### Server-owned playback and synchronized routing

The backend owns queue, transport, position, scheduling, MIDI cleanup, history emission, and WebSocket state. Implemented transport is play, pause/resume, stop, skip, and panic with automatic track advance and tempo-aware monotonic scheduling.

Multi-device routing keeps one master timeline and supports track/channel-specific routes, broadcast, TWO_PIANO, PIANO_DUET, separable DUELING_PIANO, instrument-family affinity, capacity-aware load balancing, device/role preferences, per-device latency compensation, resume priming, and conservative stop/panic behavior when a destination fails.

Curated `performance_type` and validated intent routing preferences flow into playback. Free-text `instrumentation` is not treated as a routing contract; untagged material falls back to deterministic MIDI/GM analysis.

### Responsive appliance/household UI

One no-build ES-module/CSS web application serves the 7-inch kiosk, phone, tablet, and desktop. It includes Concierge/listening surfaces, Browse, favorites, queue, Now Playing, transport, device/degraded state, live WebSocket synchronization, progress interpolation, reconnect/resync behavior, light/dark layouts, and PWA assets.

The UI is a thin client. Playback remains server-owned even if every browser disconnects.

### CI and install contracts

CI has stable check contexts:

- `lint`
- `test-py3.11`
- `test-py3.12`
- `repository-contracts`

Ruff is pinned and the rule set is explicit. Repository contracts validate schemas, device profiles, generated MIDI, importer/catalog/station flows, and now a real non-editable wheel installation.

The wheel contract boots `openorchestrion-serve` outside the checkout with physical MIDI absent, verifies health and packaged web assets, and requires graceful application shutdown. GitHub branch-protection/ruleset mutation is still an administrative step because the available repository connector does not expose that operation.

### Raspberry Pi appliance packaging

Issue #30 provides the production appliance path:

- `openorchestrion-serve` single-process production entry point;
- systemd service with restart and graceful shutdown;
- shared `/etc/openorchestrion/openorchestrion.env` runtime configuration;
- durable state under `/var/lib/openorchestrion`;
- disposable software environment under `/opt/openorchestrion/venv`;
- `openorchestrion-kiosk` health-gated Chromium startup;
- first-class headless operation;
- checkout or wheel installation/update flow;
- journald logging;
- `openorchestrion-smoke` post-install diagnostics;
- uninstall/recovery procedures that preserve library sidecars and history.

The appliance does not require Node, a CDN, Docker, or Internet access to boot and play local music.

## Current work lanes

- **Issue #9 / verified-open starter catalog:** active content/data lane on `feature/issue-9-starter-catalog`. The goal is a legally clean starter repertoire imported and tagged through the real production pipeline with per-asset source/license/attribution evidence.
- **Issues #1 and #6 / physical proof:** next platform evidence once the Pi/reference sound engine is available. Run the packaged appliance path, not a hand-launched development server.
- **Issue #11 / second Yamaha engine:** follows first-device proof and adds tone-diversity, relative-latency, two-piano, and multichannel validation.

## Next milestones

1. Complete the verified-open starter catalog (#9).
2. Install the current wheel on the reference Raspberry Pi 5 using the documented appliance procedure.
3. Run the loaded Pi timing benchmark (#6) with FastAPI, Chromium kiosk, WebSockets/library activity, and one/two MIDI outputs where available.
4. Validate the first physical sound engine end to end (#1 or the acquired equivalent): enumeration, Note On/Off, velocity, sustain, Program/Bank, GM/percussion, range, dense polyphony, endurance, reconnect/restart.
5. Validate the complementary Yamaha engine (#11) and measure relative MIDI-to-audio latency for two-device compensation.
6. After the physical reference build exists, design/publish the enclosure/BOM (#8) and capture demo evidence.
7. Publish the v2 white paper/project site (#10) after hardware photos, timing results, and demos can replace design-only claims.

## Decisions already made

- Human key feel is not a core purchasing criterion; keyboards are MIDI-addressed sound engines.
- Documented MIDI receive is mandatory for recommended hardware.
- The Pi owns one master clock for locally connected devices.
- Playback is local-first; cloud storage is for backup/recovery, not live timing.
- AI interprets intent but never directly emits MIDI.
- Core playback, selection, UI, and boot work without AI or Internet access.
- Deterministic MIDI facts, curated metadata, provenance/rights, and AI inference remain separate data classes.
- Sidecars and `history.db` are durable; `catalog.db` is rebuildable.
- The backend owns queue/playback state; browsers render and reconcile it.
- Browser progress interpolation anchors at local message receipt, not server wall-clock subtraction.
- Arbitrary imported SysEx is not executable by default.
- `performance_type` is a stable curated routing input; free-text instrumentation is advisory content, not a routing contract.
- The reference service is intended for a trusted household LAN and is not an unauthenticated public-Internet endpoint.

## Immediate proof sequence when hardware is available

1. Install/boot through the systemd appliance path and run `openorchestrion-smoke`.
2. Confirm Linux enumerates the MIDI endpoint while the service is running.
3. Send the synthetic single-note fixture and confirm internal audio playback.
4. Verify velocity response and sustain CC64.
5. Verify Program Change / Bank Select behavior and GM channel 10 percussion.
6. Exercise receive range and practical 16/32/48/64-note stress.
7. Run long-duration playback plus service restart/reconnect tests.
8. Run the Pi timing benchmark under realistic kiosk/WebSocket/library load.
9. With two sound engines, route the generated two-piano fixture from one master timeline and measure relative MIDI-to-audio latency.
10. Exercise the full Concierge → Smart Station → queue → playback → history loop against real catalog material.
