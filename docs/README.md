[Getting started](getting-started.md) · [Troubleshooting](troubleshooting.md) · [Reference build/BOM](reference-build.md)

# OpenOrchestrion Documentation

This directory contains current contracts, release evidence and future designs.
Start with the handoff and next-work index; dated release reports retain historical counts and hashes.

## Start here

- [Current issue queue](next-steps.md) — completed work, owner deferrals and actual blockers.
- [Repository maintenance record](repository-maintenance.md) — cleanup audit, validation and release identity.

- [Current developer handoff](developer-handoff.md) — shared main baseline, deployment parity, verification commands and outstanding evidence.
- [September single-keyboard release](single-keyboard-release-2026-09.md) — integration, benchmark repair, installed-wheel identity and Pi evidence.

- [Pi implementation review and fixes](implementation-review.md) — reproduced defects, fixes, validation, and explicit remaining limits.

- [Project origin](project-origin.md) — how “I want a player piano” evolved into OpenOrchestrion.
- [Architecture](architecture.md) — major components and boundaries.
- [Requirements](requirements.md) — stable FR/NFR IDs and acceptance tests.
- [Reference build](reference-build.md) — Pi 5 4 GB, 7-inch appliance display, headless alternative.
- [Raspberry Pi appliance installation](appliance-install.md) — boot-to-service systemd packaging, kiosk/headless install, updates, logs and recovery.
- [Cloudflare remote access](cloudflare-remote-access.md) — authenticated `piano.hamm.me` tunnel, exact-email Access policy, verification and recovery.
- [First-run setup and local configuration](setup-and-configuration.md) — local admin command, secrets boundary and readiness semantics; legacy setup UI is superseded by explicit Playback & devices settings.
- [Roadmap](../ROADMAP.md) — staged implementation plan.

## User experience and intelligence

- [UX and control surfaces](ux-and-control-surfaces.md)
- [Browser playback rendering controls](rendering-controls.md) — Original, Piano Only, and General MIDI channel overrides for the next queue.
- [AI Music Concierge](ai-music-concierge.md)
- [Hosted AI Music Concierge](hosted-ai-concierge.md) — optional OpenAI Responses API provider, secrets, privacy boundary and offline fallback.
- [Smart stations and selection](stations-and-selection.md)

## Application interface

- [API contract](api-contract.md) — REST/WebSocket agreement between the web UI and playback backend.
- [Playback engine](playback-engine.md) — server-owned queue, transport state machine, virtual MIDI, timing, routing, cleanup and history integration.

## MIDI and library

- [MIDI library](midi-library.md)
- [Complete-listening-v2 quality standard](library-quality-standard.md) — current admission evidence and limits.
- [Quality publication and original archive](library-quality-publication.md) — dated baseline and recovery.
- [Nightly acquisition](automatic-acquisition.md) — source registry, duplicate history, limits and operation.
- [Title and identity repair](title-metadata-repair.md) — source-name decoding, creator/context separation, embedded evidence and reversible migration.
- [Earlier v1 curation](library-curation.md) — historical policy, superseded by v2.
- [MIDI analysis and ingestion](midi-ingestion.md)
- [Rebuildable SQLite catalog](catalog.md)
- [Curating descriptive metadata](metadata-curation.md) — editable fields, atomic writes, optimistic concurrency and catalog reconciliation.
- [Music source strategy](music-sources.md)
- [Two-piano and dueling-piano mode](two-piano-and-dueling.md)
- [Test strategy](test-strategy.md)
- [MIDI conformance quickstart](midi-conformance-quickstart.md)

## Runtime state and listening history

- [Durable play history](play-history.md) — queued/started/substantial/completed semantics, no-repeat windows, staleness and backup boundaries.
- [Player workflows](player-workflows.md) — saved playlists/stations, queue editing, playback modes, seeking, timers, and restart recovery.

## Hardware

- [Hardware selection](hardware-selection.md)
- [Supported/candidate hardware](supported-hardware.md)
- [Casio CT-X700 reference profile](hardware/casio-ct-x700.md)
- [Casio WK-220 unattended playback setup](hardware/casio-wk-220.md) — disabling Auto Power Off using the keyboard's startup buttons.
- [Raspberry Pi timing benchmark protocol](pi-timing-benchmark.md) — reproducible loaded scheduler/jitter/drift evidence for Issue #6.
- Machine-readable profiles: [`../device-profiles/`](../device-profiles/)

## Multi-device and operations

- [Multi-device playback](multi-device.md)
- [Routing engine](routing-engine.md) — track/channel routing, device affinity, polyphony balancing, latency compensation and safe failure behavior.
- [Two-engine MIDI orchestra](two-engine-orchestration.md) — planned: CT-X700 as foreground engine and WK-220 as support engine, engine profiles with affinity scores, planning limits, song-specific plans, manual overrides and a visible orchestration plan.
- [Backup and recovery](backup-recovery.md)
- [Integrations and future extensions](integrations-and-future.md)

## Architecture decisions

- [ADR index](adr/README.md)

Key accepted decisions include local-first playback, treating keyboards as sound engines, isolating AI from MIDI execution, one master timeline for multiple devices, one shared web UI, rebuildable library metadata, durable history outside the rebuildable catalog, and evidence-based MIDI receive compatibility.

## White paper

- [White paper directory](whitepaper/README.md)

The Markdown documentation is authoritative and continues to evolve beyond the historical Networked Player Piano white paper.

## Documentation rule

When implementation changes one of the architectural boundaries or stable requirements, update the corresponding document/ADR in the same pull request. The goal is to keep the repository reproducible without requiring access to the original design conversation.

- [Listening room redesign](web-listening-room.md): navigation, search, MIDI performance details, deferred AI integration, and release verification.
