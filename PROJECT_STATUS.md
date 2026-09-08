# Project Status

## Phase

**Appliance-ready software / physical validation and publication**

OpenOrchestrion now has the complete local-first software path from MIDI ingestion and rights-aware curation through natural-language intent, Smart Stations, server-owned playback, multi-device routing, non-destructive rendering, responsive household control, appliance packaging, and verified backup/restore.

The software can be installed from a wheel or checkout, boot under systemd with zero MIDI hardware attached, serve its packaged UI in headless or Chromium-kiosk mode, and pass repository contracts from a non-editable installation.

The WK-220 checklist and a loaded 120-minute headless Pi software timing run are recorded. Remaining physical evidence covers local kiosk load, measured MIDI-to-audio latency, unavailable CT-X700/second-engine hardware, and enclosure/BOM. See [the current issue dispositions](docs/next-steps.md).

## Current deployed handoff

The [0.1.0 release](docs/releases/0.1.0.md) packages the single-keyboard software and
adds guided source selection, bounded acquisition, progress and retry from the browser.
See [release installation/upgrades](docs/releases.md) and [guided acquisition](docs/guided-acquisition.md).

The [developer handoff](docs/developer-handoff.md) identifies the shared `main` baseline, exact deployed source, validation evidence and remaining limits. [PR #85](https://github.com/kurthamm/openorchestrion/pull/85) merged the reliability, curated library and listening-room changes on September 7. The [single-keyboard release record](docs/single-keyboard-release-2026-09.md) tracks its CI, installed wheel and Pi timing evidence.

The [complete-listening v2 release](docs/library-quality-publication.md) is deployed:
**5,832 performances were retained from 25,893 originals assessed**. All other originals
remain in the recovery archive. Publisher verification and independent arrangement
assessment are labeled separately, with per-file decisions and playback details.
The integrated release preserves the durable player workflows and PR #91 off-site
backup support. That historical build passed 704 tests with 101 matching runtime files.
The earlier [readiness release](docs/library-playback-readiness.md) remains historical
timing and compatibility evidence. Source admission does not certify acoustic fidelity.

[Automatic acquisition](docs/automatic-acquisition.md) is now deployed and scheduled
daily at 04:30–04:45 America/New_York. Five tested sources feed the existing v2
quality gate; duplicate history covers all originals and subsequent decisions.
The first run added **29 performances**, giving **5,861 available as of September 7**; the live API reports later growth. It rejected
50 candidates and skipped 7 duplicates. No original archives were deleted.
The release integrates PR #93 player operations, passes **726 tests**, and has
**107 deployed runtime files matching source** at that release. The [maintenance record](docs/repository-maintenance.md) records subsequent fixes and validation. Source failures and run results are
visible in Playback & devices; the acquisition database survives normal backup.

## Implemented product stack

The [title metadata repair](docs/title-metadata-repair.md) corrected **2,230 titles**
and updated identity metadata on **4,190 records**, retaining all **5,861 songs**.
Imports now normalize encoded labels; the UI separates source context and creator
credits and exposes original labels and evidence. Four researched upload labels
remain explicitly unresolved. The repair record contains deployment and rollback details.

The [September 2026 Pi implementation review](docs/implementation-review.md) records
fixes for event-loop blocking, MIDI discovery after startup, favorite state, restore
failure recovery, and smoke-check diagnostics. Deployment/profile binding and physical
validation limits are listed there separately from completed software work.

### Library, analysis, and curation

- SHA-256 content-addressed MIDI assets with authoritative JSON sidecars.
- Robust batch importer that isolates malformed/truncated/oversized inputs rather than aborting a collection.
- Deterministic analyzer for timing, tracks/channels, programs/banks, controllers, sustain, percussion, note range, expressive events, SysEx presence, and sustain-aware peak simultaneous voices.
- `openorchestrion-tag` single-asset and SHA-256-keyed CSV metadata editing.
- Atomic metadata writes with optimistic revisions plus per-asset writer locking.
- `openorchestrion-reanalyze` for repairing deterministic analysis without re-importing immutable MIDI objects.
- Rebuildable `catalog.db` with composition/performance separation and per-asset reconciliation.
- Durable favorites and curated metadata that survive catalog deletion/rebuild.
- Automated reversible admission: the initial 5,832-performance selection plus 29 newly acquired performances, with 20,061 original files archived; rebuild and single-asset reindex enforce the v2 admission list. Complete original-library publication and restoration were rehearsed with all hashes verified.

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
- Music-first Discover, paginated library search with combined filters, dedicated Favorites, Queue and Recently Played, MIDI performance details, persistent transport, live progress, reconnect/resync, and explicit Playback & devices settings.
- AI is deliberately absent from the current browser. The existing Concierge backend remains available for a future optional interface.
- Browser rendering preference is explicitly local preference for the next queue, not authoritative server playback state.
- No Node build, CDN, webfont, or external runtime resource dependency.

### Appliance setup and LAN discovery

- `openorchestrion-serve` single-process production entry point.
- systemd service with graceful shutdown and journald logging.
- Durable state under `/var/lib/openorchestrion`; software environment under `/opt/openorchestrion/venv`.
- Headless and health-gated Chromium kiosk modes.
- Explicit Playback & devices view for readiness and sound settings; no forced first-run redirect. Legacy setup APIs remain compatible.
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
- `test-py3.13`
- `repository-contracts`

Ruff version and selected rule set are explicit. Repository contracts validate schemas, device profiles, generated MIDI, import/catalog/station flows, rights policy, and a non-editable wheel installation.

The wheel contract boots the packaged server outside the source checkout with no physical MIDI output, verifies health and web assets, and requires graceful shutdown.

GitHub `main` branch protection remains an administrative repository-setting step; the connected repository tool does not expose that mutation.

## Current reference hardware status

The software is hardware-neutral and routes by capability/profile rather than model-name branches.

The project has manufacturer-evidence profiles and procurement candidates from Casio and Yamaha families. The Casio CT-X700 remains the named hardware-proof issue/reference profile, while other used Casio/Yamaha models are being considered for the first practical two-engine build.

The connected WK-220 has recorded checklist/headless timing evidence, with its exact scope in [supported hardware](docs/supported-hardware.md). Manufacturer evidence for other devices is not physical project validation. CT-X700 work remains owner-deferred.

## Current work lanes

See the [issue-based next-work review](docs/next-steps.md) for the recommended order and the WK-220 hardware results already reported in issue #1.

- **Integrated:** the deployed listening-room branch is merged into `main`; the primary Pi checkout follows that baseline. Current validation covers the existing WK-220 setup, with the exact result and limits in the single-keyboard release record.
- **Issue #84:** deferred by the owner until the new keyboard is available, together with CT-X700 validation and physical two-engine testing. Retain the orchestration plan for later; do not implement its UI or policy now.


- **Issue #64:** deepen genuine chamber/orchestral starter repertoire. Source reports now keep instrumentation/arrangement clues independent from rights lines so an ensemble score is not confused with a keyboard reduction.
- **Issue #10:** publication lane. The first slice creates the OpenOrchestrion v2 living white paper and static project site while keeping hardware photos/results explicitly pending.
- **Issue #6:** the headless WK-220 loaded 120-minute run passed all software targets; raw JSON and environmental evidence are committed in the release record. Kiosk/two-output and acoustic evidence remain separate, so the broader issue stays open.
- **Issue #1:** the WK-220 checklist was previously reported passed; CT-X700-specific proof remains deferred. The new headless endurance evidence does not replace acoustic/conformance measurements.
- **Issue #11:** complementary Yamaha/second-engine validation follows first-engine proof.
- **Issue #8:** reference enclosure/BOM follows acquisition of the physical build.

## Remaining physical proof sequence

Completed prerequisites: packaged Pi installation, smoke checks, WK-220 enumeration,
reported controller/playback/reconnect checklist, and loaded headless endurance evidence.

When the required setup becomes available:

1. Capture local Chromium kiosk load and measured MIDI-to-audio latency.
2. Validate the new keyboard on its own checklist, then measure relative engine latency.
3. Resume owner-deferred orchestration and physical split/two-piano tests.
4. Finalize the measured enclosure/BOM and capture hardware photos/demo video.
5. Update publication claims from those measurements.

## Publication status

The living OpenOrchestrion v2 Markdown white paper and project-site source describe implemented software and recorded WK-220/headless evidence. GitHub Pages Actions publishing is enabled; the maintenance release records public deployment verification for #10. Final publication media remains intentionally incomplete until hardware evidence is available.

The project site must distinguish three levels of claim:

1. **Implemented software:** behavior present and tested in the repository.
2. **Documented compatibility:** manufacturer/source evidence indicates a capability.
3. **Project validated:** physical OpenOrchestrion evidence has been captured.

That distinction is part of the engineering standard, not a footnote.
