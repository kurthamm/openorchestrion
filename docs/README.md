# OpenOrchestrion Documentation

This directory contains the living design and implementation specification.

## Start here

- [Project origin](project-origin.md) — how “I want a player piano” evolved into OpenOrchestrion.
- [Architecture](architecture.md) — major components and boundaries.
- [Requirements](requirements.md) — stable FR/NFR IDs and acceptance tests.
- [Reference build](reference-build.md) — Pi 5 4 GB, 7-inch appliance display, headless alternative.
- [Raspberry Pi appliance installation](appliance-install.md) — boot-to-service systemd packaging, kiosk/headless install, updates, logs and recovery.
- [First-run setup and local configuration](setup-and-configuration.md) — secure Setup screen, local admin command, secrets boundary and readiness semantics.
- [Roadmap](../ROADMAP.md) — staged implementation plan.

## User experience and intelligence

- [UX and control surfaces](ux-and-control-surfaces.md)
- [AI Music Concierge](ai-music-concierge.md)
- [Hosted AI Music Concierge](hosted-ai-concierge.md) — optional OpenAI Responses API provider, secrets, privacy boundary and offline fallback.
- [Smart stations and selection](stations-and-selection.md)

## Application interface

- [API contract](api-contract.md) — REST/WebSocket agreement between the web UI and playback backend.
- [Playback engine](playback-engine.md) — server-owned queue, transport state machine, virtual MIDI, timing, routing, cleanup and history integration.

## MIDI and library

- [MIDI library](midi-library.md)
- [MIDI analysis and ingestion](midi-ingestion.md)
- [Rebuildable SQLite catalog](catalog.md)
- [Curating descriptive metadata](metadata-curation.md) — editable fields, atomic writes, optimistic concurrency and catalog reconciliation.
- [Music source strategy](music-sources.md)
- [Two-piano and dueling-piano mode](two-piano-and-dueling.md)
- [Test strategy](test-strategy.md)
- [MIDI conformance quickstart](midi-conformance-quickstart.md)

## Runtime state and listening history

- [Durable play history](play-history.md) — queued/started/substantial/completed semantics, no-repeat windows, staleness and backup boundaries.

## Hardware

- [Hardware selection](hardware-selection.md)
- [Supported/candidate hardware](supported-hardware.md)
- [Casio CT-X700 reference profile](hardware/casio-ct-x700.md)
- [Raspberry Pi timing benchmark protocol](pi-timing-benchmark.md) — reproducible loaded scheduler/jitter/drift evidence for Issue #6.
- Machine-readable profiles: [`../device-profiles/`](../device-profiles/)

## Multi-device and operations

- [Multi-device playback](multi-device.md)
- [Routing engine](routing-engine.md) — track/channel routing, device affinity, polyphony balancing, latency compensation and safe failure behavior.
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
