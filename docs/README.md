# OpenOrchestrion Documentation

This directory contains the living design and implementation specification.

## Start here

- [Project origin](project-origin.md) — how “I want a player piano” evolved into OpenOrchestrion.
- [Architecture](architecture.md) — major components and boundaries.
- [Requirements](requirements.md) — stable FR/NFR IDs and acceptance tests.
- [Reference build](reference-build.md) — Pi 5 4 GB, 7-inch appliance display, headless alternative.
- [Roadmap](../ROADMAP.md) — staged implementation plan.

## User experience and intelligence

- [UX and control surfaces](ux-and-control-surfaces.md)
- [AI Music Concierge](ai-music-concierge.md)
- [Smart stations and selection](stations-and-selection.md)

## MIDI and library

- [MIDI library](midi-library.md)
- [MIDI analysis and ingestion](midi-ingestion.md)
- [Music source strategy](music-sources.md)
- [Two-piano and dueling-piano mode](two-piano-and-dueling.md)
- [Test strategy](test-strategy.md)
- [MIDI conformance quickstart](midi-conformance-quickstart.md)

## Hardware

- [Hardware selection](hardware-selection.md)
- [Supported/candidate hardware](supported-hardware.md)
- [Casio CT-X700 reference profile](hardware/casio-ct-x700.md)
- Machine-readable profiles: [`../device-profiles/`](../device-profiles/)

## Multi-device and operations

- [Multi-device playback](multi-device.md)
- [Backup and recovery](backup-recovery.md)
- [Integrations and future extensions](integrations-and-future.md)

## Architecture decisions

- [ADR index](adr/README.md)

Key accepted decisions include local-first playback, treating keyboards as sound engines, isolating AI from MIDI execution, one master timeline for multiple devices, one shared web UI, rebuildable library metadata, and evidence-based MIDI receive compatibility.

## White paper

- [White paper directory](whitepaper/README.md)

The Markdown documentation is authoritative and continues to evolve beyond the historical Networked Player Piano white paper.

## Documentation rule

When implementation changes one of the architectural boundaries or stable requirements, update the corresponding document/ADR in the same pull request. The goal is to keep the repository reproducible without requiring access to the original design conversation.
