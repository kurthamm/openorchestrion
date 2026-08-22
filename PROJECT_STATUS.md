# Project Status

## Phase

**Software foundation / hardware acquisition and validation**

OpenOrchestrion now has executable MIDI generation, analysis, ingestion, a rebuildable catalog, deterministic Smart Stations, durable play history, and the provider-neutral Music Concierge intent pipeline. The first end-to-end physical build is still pending acquisition of the target sound engines.

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

Listening behavior is stored separately from the rebuildable catalog in `history.db`.

Implemented behavior includes queued/started/substantially-played/completed/skipped/failed lifecycle states, meaningful-play thresholds, recent asset/composition lookup for no-repeat windows, play-count/last-played summaries, staleness ranking, Smart Station exclusion helpers, schema versioning, and backup/recovery separation from `catalog.db`.

### AI Music Concierge intent pipeline

Natural-language control now has a provider-neutral, strictly validated boundary.

Implemented behavior includes:

- `MusicConciergeProvider` abstraction
- minimal `IntentBackend` seam for future hosted/local structured-output models
- `ValidatingJSONConciergeProvider` for JSON/model output
- strict `PlaybackIntent` validation with unknown fields forbidden
- preservation checks for hard include/exclude tags on refinement turns
- `ConciergeSession` for conversational current-intent state
- resilient primary-provider → deterministic-fallback behavior
- offline deterministic interpretation for core household requests
- duration, dinner, Christmas, cocktail, classical, jazz, ragtime/Joplin, familiarity, energy, piano, orchestra, two-piano, and dueling-piano interpretation
- no AI/provider access to catalog mutation, playback engines, or MIDI ports

Example offline/fallback command:

```bash
openorchestrion-concierge "Play popular Christmas music while we eat, mostly piano" --json
```

The resulting `PlaybackIntent` can be passed directly into the deterministic Smart Station engine. Provider-specific hosted/local integrations remain replaceable adapters rather than architectural dependencies.

## Next software dependencies

1. **Playback state machine and virtual MIDI outputs** — own the active queue, play/pause/stop/skip/panic state, emit history events, advance between tracks, and exercise MIDI scheduling without physical keyboards.
2. **Responsive web/API layer** — appliance/phone interface driven by one server-side playback state and WebSocket updates.
3. **Hosted/local AI provider adapter(s)** — optional concrete integrations behind the already-implemented `IntentBackend` seam.
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
- Unknown AI/model fields fail closed at the PlaybackIntent boundary rather than being ignored.
- Hosted/local model selection is an adapter concern and cannot change MIDI execution architecture.

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
14. Exercise the Music Concierge against the real catalog and Smart Station selector.
