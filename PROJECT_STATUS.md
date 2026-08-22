# Project Status

## Phase

**Software foundation / hardware acquisition and validation**

OpenOrchestrion now has a detailed design baseline plus executable MIDI generation, analysis, ingestion, catalog, deterministic Smart Station selection, and durable play history. The first end-to-end physical build is still pending acquisition of the target sound engines.

## Current hardware targets

The current intended first two-engine build is:

1. **Casio CTK-6200** — primary/general ensemble engine.
2. **Yamaha PSR-EW300** — complementary Yamaha sound engine.

Both are documented MIDI-receiving candidates with nominal 48-note polyphony and broad sound sets. They are being targeted because the pair provides two independent synthesis engines and two different manufacturer sound palettes, not because of physical key count or human key feel.

**Status:** acquisition pending; physical project validation pending.

The earlier **Casio CT-X700** investigation remains a documented-compatible fallback/reference and produced the project's first detailed hardware evidence/profile example.

## Implemented software foundation

### Synthetic MIDI conformance generator

OpenOrchestrion can generate a copyright-clean test laboratory including single-note, velocity, sustain, Program Change/Bank Select, GM ensemble/percussion, full note-range, polyphony stress, two-piano split, sync-click, endurance, and parser-resilience fixtures.

### Deterministic MIDI analyzer

Implemented analysis includes file identity, SMF format/timing, duration/tempo, tracks/channels, programs/banks, controllers/sustain, percussion, note/velocity statistics, pitch bend/aftertouch, SysEx count, sustain-aware estimated peak simultaneous MIDI notes, and generic compatibility/complexity flags.

### Durable MIDI importer

The importer provides recursive discovery, SHA-256 content-addressed storage, duplicate/idempotent import behavior, rights/provenance capture, durable JSON sidecars, and strict separation of deterministic analysis, curated metadata, and future AI enrichment.

### Rebuildable SQLite catalog

The catalog can be recreated from durable sidecars at any time. It indexes compositions separately from individual MIDI performances plus descriptive metadata, rights/provenance, MIDI structure, and compatibility-relevant facts. Rebuilding is atomic so an invalid sidecar cannot destroy the last known-good index.

### Deterministic Smart Station engine

Structured `PlaybackIntent` can produce an explainable queue without AI or hardware. The selector supports exact/partial/fallback matching, weighted preferences, hard exclusions, device/MIDI constraints, best-performance-per-composition selection, composer diversity, duration targets, seeded variation, per-item score explanations, and explicit soft-preference relaxation.

Example:

```bash
openorchestrion-station var/library/catalog.db \
  --theme dinner \
  --energy low \
  --duration-minutes 120 \
  --seed 42
```

### Durable play history

Listening behavior is now stored separately from the rebuildable catalog in `history.db`.

Implemented behavior includes:

- queued / started / substantially-played / completed / skipped / failed lifecycle states
- substantial-listen threshold before a partial play counts for no-repeat/history
- completed tracks always count
- quick skips and queued-only items do not count as played
- append-only meaningful lifecycle events plus current play-attempt summary state
- recent asset/composition lookup for configurable no-repeat windows
- per-asset play count, last-played, total listened time, completions, and substantial skips
- staleness ranking for “not heard recently” behavior
- helper to merge recent history into `StationConstraints`
- explicit history schema versioning
- backup/recovery separation from rebuildable `catalog.db`

Example:

```bash
openorchestrion-history var/history.db recent --days 30
```

## Next software dependencies

1. **AI Music Concierge** — translate natural language into/refine `PlaybackIntent` and hand it to the deterministic selector.
2. **Playback state machine and virtual MIDI outputs** — queue, play, pause, stop, skip, panic, history-event emission, and hardware-neutral playback state before physical keyboards arrive.
3. **Responsive web UI** — appliance/phone interface driven by the same API and WebSocket state.
4. **CI and schema/test automation** — run the non-hardware regression suite automatically on GitHub.

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
- Listening history is durable runtime state and is not stored solely in the rebuildable catalog.

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
