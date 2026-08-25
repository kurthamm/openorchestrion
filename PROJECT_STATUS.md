# Project Status

## Phase

**Appliance-ready software / physical validation and publication**

OpenOrchestrion now has the complete local-first software path from MIDI ingestion and rights-aware curation through natural-language intent, Smart Stations, server-owned playback, multi-device routing, non-destructive rendering, responsive household control, appliance packaging, and verified backup/restore.

The software can be installed from a wheel or checkout, boot under systemd with zero MIDI hardware attached, serve its packaged UI in headless or Chromium-kiosk mode, and pass repository contracts from a non-editable installation.

The major remaining engineering evidence is physical rather than architectural: Raspberry Pi timing under realistic appliance load, end-to-end MIDI/audio validation on the selected sound engines, relative MIDI-to-audio latency for two-engine synchronization, and the reference enclosure/BOM.

## Implemented product stack

### Library, analysis, and curation

- SHA-256 content-addressed MIDI assets with authoritative JSON sidecars.
- Robust batch importer that isolates malformed/truncated/oversized inputs rather than aborting a collection.
- Deterministic analyzer for timing, tracks/channels, programs/banks, controllers, sustain, percussion, note range, expressive events, SysEx presence, and sustain-aware peak simultaneous voices.
- `openorchestrion-tag` single-asset and SHA-256-keyed CSV metadata editing.
- Atomic metadata writes with optimistic revisions plus per-asset writer locking.
- `openorchestrion-reanalyze` for repairing deterministic analysis without re-importing immutable MIDI objects.
- Rebuildable `catalog.db` with composition/performance separation and per-asset reconciliation.
- Durable favorites and curated metadata that survive catalog deletion/rebuild.

### Rights and starter repertoire

- Separate evidence for composition rights and the specific MIDI file/arrangement license.
- Fail-closed `verified-open` audit and post-import rights editing.
- CI audits Git-tracked MIDI repository-wide rather than trusting one directory.
- Source-reading and candidate-fetch workflows support evidence-based curation without guessing archive terms.
- A verified-open starter repertoire now ships through the same import/tag/reindex path used by ordinary libraries.
- Issue #64 is expanding the still-thin chamber/orchestral category with instrumentation evidence kept separate from rights evidence.

### Smart Stations and listening history

- Strict `PlaybackIntent` with deterministic station construction.
- Exact/partial/fallback matching, hard compatibility constraints, weighted preferences, favorites, quality, seeded variation, composer diversity, energy sequencing, duration targets, and explicit relaxation diagnostics.
- Durable `history.db` with queued/started/substantial/completed/skipped/failed semantics.
- No-repeat and staleness inputs feed station selection.

### AI Music Concierge

- Provider-neutral intent interpretation with bounded conversational refinement.
- Deterministic offline interpreter remains available without Internet access.
- Optional hosted OpenAI Responses API adapter with strict structured output and hard-tag preservation.
- Hosted AI is explicit opt-in; merely storing a provider key does not enable cloud calls.
- Prompts/current intent may leave the appliance only when hosted AI is enabled. MIDI files, queue, history, devices, MIDI events, and audio are not part of the interpretation contract.
- Provider credentials live in a service-only secrets file and do not appear in browser status/configuration.

### Server-owned playback

- Authoritative queue and transport state machine with play/resume, pause, stop, skip, panic, and automatic advance.
- Tempo-aware monotonic scheduling through the clock seam.
- Idempotent command IDs and WebSocket state snapshots/deltas.
- Browser progress interpolation anchors at local message receipt rather than subtracting server wall clock.
- Resume primes channel state without pretending held notes persisted through pause.
- Arbitrary imported SysEx is suppressed by default.

### Synchronized routing and rendering

- One master timeline drives all directly attached sound engines.
- Track/channel routes, broadcast, instrument-family affinity, device capabilities, load balancing, role/device preferences, and per-device latency offsets.
- `SOLO_PIANO`, `MULTI_INSTRUMENT`, `PIANO_DUET`, `TWO_PIANO`, `DUELING_PIANO`, and future `DISTRIBUTED` performance types.
- Conservative stop/panic if an active required destination disappears.
- Non-destructive `ORIGINAL`, `PIANO_ONLY`, and `OVERRIDE` rendering modes.
- Rendering occurs before routing so the planner sees the program family that will actually sound.
- The browser now exposes rendering controls for the next queue using the backend-owned General MIDI vocabulary rather than a duplicate 128-program table.

### Responsive household UI

- One no-build HTML/CSS/ES-module application for 800×480 kiosk, phones, tablets, and desktop browsers.
- Concierge, station shortcuts, Browse/search, favorites, Queue, History, Now Playing, transport, health/degraded states, live progress, reconnect/resync, setup, and rendering controls.
- Browser rendering preference is explicitly local preference for the next queue, not authoritative server playback state.
- No Node build, CDN, webfont, or external runtime resource dependency.

### Appliance setup and LAN discovery

- `openorchestrion-serve` single-process production entry point.
- systemd service with graceful shutdown and journald logging.
- Durable state under `/var/lib/openorchestrion`; software environment under `/opt/openorchestrion/venv`.
- Headless and health-gated Chromium kiosk modes.
- First-run Setup view for readiness and next actions.
- Privileged `openorchestrion-configure` for settings/secrets that must not be writable from an unauthenticated household browser.
- Optional Avahi/mDNS discovery and explicit `openorchestrion.local` hostname path.
- `openorchestrion-smoke` verifies the installed appliance without requiring physical MIDI hardware.

### Backup and recovery

- Versioned application-data archive for immutable MIDI objects, sidecars, and a SQLite-safe history snapshot.
- `catalog.db` is deliberately excluded and rebuilt on restore.
- Backup publication is atomic and verifies content-address integrity before replacement.
- Restore rejects path traversal, unexpected members, symlinks, duplicates, digest mismatches, malformed sidecars, corrupt history, unsupported versions, and raced/non-empty targets.
- Privileged replacement workflow performs preflight before stopping a healthy service, creates a rollback backup, publishes verified candidate state, health-checks the replacement, and restores the old tree if the new state cannot become healthy.
- Provider secrets and system configuration are not silently included in application-data backups.

### CI and packaging contracts

Stable CI contexts are:

- `lint`
- `test-py3.11`
- `test-py3.12`
- `repository-contracts`

Ruff version and selected rule set are explicit. Repository contracts validate schemas, device profiles, generated MIDI, import/catalog/station flows, rights policy, and a non-editable wheel installation.

The wheel contract boots the packaged server outside the source checkout with no physical MIDI output, verifies health and web assets, and requires graceful shutdown.

GitHub `main` branch protection remains an administrative repository-setting step; the connected repository tool does not expose that mutation.

## Current reference hardware status

The software is hardware-neutral and routes by capability/profile rather than model-name branches.

The project has manufacturer-evidence profiles and procurement candidates from Casio and Yamaha families. The Casio CT-X700 remains the named hardware-proof issue/reference profile, while other used Casio/Yamaha models are being considered for the first practical two-engine build.

**No keyboard is promoted to project-validated hardware until physical evidence exists.** Manufacturer documentation is evidence of documented compatibility, not a substitute for the project's own enumeration, controller, polyphony, reconnect, latency, and long-run tests.

## Current work lanes

- **Issue #64:** deepen genuine chamber/orchestral starter repertoire. Source reports now keep instrumentation/arrangement clues independent from rights lines so an ensemble score is not confused with a keyboard reduction.
- **Issue #10:** publication lane. The first slice creates the OpenOrchestrion v2 living white paper and static project site while keeping hardware photos/results explicitly pending.
- **Issue #6:** timing harness is implemented; the controlled Raspberry Pi 5 loaded run remains open.
- **Issue #1:** physical first-engine proof remains open.
- **Issue #11:** complementary Yamaha/second-engine validation follows first-engine proof.
- **Issue #8:** reference enclosure/BOM follows acquisition of the physical build.

## Next physical proof sequence

1. Install the current wheel on the reference Raspberry Pi through the documented systemd path.
2. Run `openorchestrion-smoke` before attaching MIDI hardware.
3. Attach the first sound engine and capture Linux MIDI enumeration.
4. Verify Note On/Off, velocity, sustain CC64, Program Change, Bank Select, GM/percussion, receive range, practical 16/32/48/64-note stress, and expressive piano playback.
5. Exercise service restart, reconnect, power-cycle, and long-duration playback.
6. Run the controlled Pi timing protocol with FastAPI, Chromium kiosk where applicable, WebSockets/library activity, and output paths active.
7. Attach the second sound engine and measure relative MIDI-to-audio latency.
8. Route two-piano/duet and multichannel material from the one master timeline.
9. Publish the enclosure/BOM and capture hardware photos/demo video.
10. Update the v2 publication with measured evidence rather than design-only claims.

## Publication status

The living OpenOrchestrion v2 Markdown white paper and project site can describe implemented software now. Final publication media remains intentionally incomplete until hardware evidence is available.

The project site must distinguish three levels of claim:

1. **Implemented software:** behavior present and tested in the repository.
2. **Documented compatibility:** manufacturer/source evidence indicates a capability.
3. **Project validated:** physical OpenOrchestrion evidence has been captured.

That distinction is part of the engineering standard, not a footnote.
