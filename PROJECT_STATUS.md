# Project Status

## Phase

**Software foundation / hardware acquisition and validation**

OpenOrchestrion now has a detailed design baseline plus the first executable MIDI tooling. The first end-to-end physical build is still pending acquisition of the target sound engines.

## Current hardware targets

The current intended first two-engine build is:

1. **Casio CTK-6200** — primary/general ensemble engine.
2. **Yamaha PSR-EW300** — complementary Yamaha sound engine.

Both are documented MIDI-receiving candidates with nominal 48-note polyphony and broad sound sets. They are being targeted because the pair provides two independent synthesis engines and two different manufacturer sound palettes, not because of physical key count or human key feel.

**Status:** acquisition pending; physical project validation pending.

The earlier **Casio CT-X700** investigation remains a documented-compatible fallback/reference and produced the project's first detailed hardware evidence/profile example.

## Implemented software foundation

### Synthetic MIDI conformance generator

OpenOrchestrion can generate a copyright-clean test laboratory including:

- single note
- velocity ladder
- sustain CC64
- Program Change / Bank Select
- GM multichannel ensemble + channel 10 percussion
- MIDI note range 0–127
- 16/32/48/64-note polyphony stress
- two-piano split
- synchronization clicks
- long-run endurance material
- parser-resilience events

### Deterministic MIDI analyzer

Implemented analysis includes:

- SHA-256/file identity
- SMF format/timing
- duration and tempo map
- tracks/channels
- Program Change / Bank Select with GM names
- controllers and sustain
- percussion
- note/velocity statistics
- pitch bend and aftertouch
- SysEx count
- sustain-aware estimated peak simultaneous MIDI notes
- generic compatibility/complexity flags

### Durable MIDI importer

The importer now provides:

- recursive file discovery
- SHA-256 content-addressed storage
- exact duplicate/idempotent import behavior
- rights/provenance capture
- durable JSON sidecars
- strict separation of deterministic analysis, curated metadata, and future AI enrichment

The searchable SQLite catalog remains the next library layer and will be rebuildable from durable sidecars rather than becoming the only copy of metadata.

## Decisions already made

- Human key feel is not a core purchasing criterion.
- Documented MIDI receive is mandatory for recommended hardware.
- The Pi owns the master clock for locally connected devices.
- Playback is local-first; cloud storage is for backup/recovery, not live timing.
- The library stores provenance and rights metadata.
- Multi-device routing is first-class even if v1 uses one device.
- Device-specific latency compensation is part of the routing model.
- Natural-language music selection is a core feature via the AI Music Concierge.
- AI interprets intent but does not directly emit MIDI.
- Core playback must work without AI or Internet access.
- Deterministic MIDI facts, human-curated metadata, and AI inference remain distinct data classes.

## Immediate proof-of-concept tests when hardware arrives

1. Confirm Linux enumerates each USB MIDI device.
2. Send the synthetic single-note fixture and confirm internal audio playback.
3. Verify velocity response.
4. Verify sustain (CC64).
5. Verify Program Change / Bank Select behavior.
6. Play the generated GM multichannel fixture.
7. Verify channel 10 percussion.
8. Exercise MIDI note receive range beyond the physical keybed where supported.
9. Stress practical polyphony/voice stealing at 16/32/48/64 simultaneous notes.
10. Run long-duration continuous playback.
11. Power-cycle and verify automatic recovery.
12. With both keyboards, test synchronized split routing and measure relative latency.
13. Route the generated two-piano fixture independently to the two engines.
14. Exercise the AI Music Concierge against deterministic library results.
