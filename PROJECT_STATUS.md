# Project Status

## Phase

**Software foundation / hardware acquisition and validation**

OpenOrchestrion now has a detailed design baseline plus executable MIDI generation, analysis, ingestion, catalog, and deterministic Smart Station selection. The first end-to-end physical build is still pending acquisition of the target sound engines.

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

The importer provides:

- recursive file discovery
- SHA-256 content-addressed storage
- exact duplicate/idempotent import behavior
- rights/provenance capture
- durable JSON sidecars
- strict separation of deterministic analysis, curated metadata, and future AI enrichment

### Rebuildable SQLite catalog

The catalog can now be recreated from durable sidecars at any time. It indexes:

- compositions separately from individual MIDI performances
- title/composer/artist/era
- genres, moods, themes, tags, and instrumentation
- performance type and quality grade
- familiarity, energy, and favorites
- rights/provenance
- duration, channels, tracks, programs, note range, sustain, percussion, and peak simultaneous notes

Catalog rebuilding is atomic so an invalid sidecar cannot destroy the last known-good index.

### Deterministic Smart Station engine

Structured `PlaybackIntent` can now produce an explainable queue without AI or attached hardware. The selector implements:

- exact / partial / fallback metadata matching tiers
- genre, mood, theme, era, instrumentation, and performance-type matching
- composer/artist preference weighting
- familiarity, energy, favorite, and quality scoring
- hard include/exclude tags
- rights and MIDI/device eligibility constraints
- one preferred MIDI performance per composition
- composer diversity and energy-transition penalties
- requested-duration/overshoot consideration
- deterministic seeded variation for reproducible tests
- per-item score breakdown and selection reasons
- explicit soft-preference relaxation diagnostics
- hooks for recent asset/composition exclusions

Example command:

```bash
openorchestrion-station var/library/catalog.db \
  --theme dinner \
  --energy low \
  --duration-minutes 120 \
  --seed 42
```

## Next software dependencies

1. **Durable play history** — record what was actually played, calculate no-repeat windows, and provide rarely-played/last-played weighting.
2. **AI Music Concierge** — translate natural language into/refine `PlaybackIntent` and hand it to the deterministic selector.
3. **Playback state machine and virtual MIDI outputs** — queue, play, pause, stop, skip, panic, and hardware-neutral playback state before physical keyboards arrive.
4. **Responsive web UI** — appliance/phone interface driven by the same API and WebSocket state.

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
- SQLite catalog data is rebuildable and is not the sole durable source of music metadata.
- Smart Station selection is deterministic, explainable, and independently testable from AI.

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
