# Project Status

## Phase

**Software foundation / hardware acquisition and validation**

OpenOrchestrion now has executable MIDI generation, deterministic analysis and ingestion, a rebuildable catalog, Smart Stations, durable play history, the provider-neutral Music Concierge, an HTTP/WebSocket application contract, and a server-owned playback engine with virtual MIDI support. The first end-to-end physical build is still pending acquisition of the target sound engines.

## Current hardware targets

The intended first two-engine build is:

1. **Casio CTK-6200** — primary/general ensemble engine.
2. **Yamaha PSR-EW300** — complementary Yamaha sound engine.

Both are documented MIDI-receiving candidates with nominal 48-note polyphony and broad sound sets. Acquisition and physical project validation are still pending. The earlier Casio CT-X700 remains a documented-compatible fallback/reference.

## Implemented software foundation

### Synthetic MIDI conformance generator

Generates copyright-clean single-note, velocity, sustain, Program Change/Bank Select, GM ensemble/percussion, full note-range, polyphony stress, two-piano split, synchronization, endurance, and parser-resilience fixtures.

### Deterministic MIDI analyzer and durable importer

Provides SHA-256 identity, timing/tempo, tracks/channels, programs/banks, controllers, sustain, percussion, note/velocity statistics, expressive-event/SysEx reporting, estimated peak simultaneous MIDI notes, content-addressed storage, durable sidecars, and rights/provenance separation.

### Rebuildable SQLite catalog

Rebuilds atomically from durable sidecars and indexes compositions separately from individual MIDI performances plus descriptive metadata, provenance, and compatibility-relevant MIDI facts.

### Deterministic Smart Stations

Validated `PlaybackIntent` produces explainable queues with exact/partial/fallback matching, weighted preferences, hard exclusions, composer diversity, duration targets, device/MIDI limits, seeded variation, and explicit relaxation diagnostics.

### Durable play history

`history.db` remains separate from the rebuildable catalog. It records queued, started, substantially played, completed, skipped, and failed attempts and feeds no-repeat/staleness behavior back into station selection.

### AI Music Concierge

Provider-neutral natural-language interpretation produces strictly validated `PlaybackIntent`, preserves hard constraints during refinement, supports bounded conversational sessions, and falls back to deterministic offline interpretation without giving an AI provider access to MIDI or playback execution.

### HTTP/WebSocket application contract

The FastAPI layer exposes catalog, history, Concierge, station preview, queue, transport, device/status, and typed WebSocket state. Command IDs are UUID-validated and successful mutations are idempotent by command ID.

### Server-owned playback engine

Issue #14 implementation now provides:

- canonical queue and current-index ownership;
- play, pause/resume, stop, skip, and panic;
- automatic track advance;
- monotonic scheduling with a deterministic manual test clock;
- tempo-aware MIDI timelines;
- virtual in-memory and lazy physical Mido outputs behind one abstraction;
- reuse of `RoutingPlan` for channel-to-device routing;
- one master timeline for multi-device playback;
- positive per-route latency compensation;
- cleanup fan-out using sustain-off, All Sound Off, and All Notes Off;
- durable history emission for queue/start/progress/completion/skip/failure;
- no-repeat history integration during station/queue generation;
- command-id idempotency;
- server-owned state that survives browser disconnects;
- typed WebSocket snapshots and state deltas;
- safe missing-file/output failure behavior;
- arbitrary imported SysEx suppressed by default;
- orderly application shutdown stops active playback before closing outputs.

Hardware-free development can enable:

```bash
OPENORCHESTRION_VIRTUAL_MIDI=1
```

which exposes `OpenOrchestrion Virtual` while retaining the same queue, transport, history, routing, and WebSocket architecture.

## Current parallel work lanes

- **Issue #14 / playback backend:** implementation and review on `feature/issue-14-playback`.
- **Issue #5 / responsive web UI:** separate frontend lane using the merged API contract; frontend does not own playback or MIDI state.

## Next software dependencies

1. Finish review/merge of Issue #14.
2. Build the responsive 7-inch/household web UI for Issue #5.
3. Implement the durable descriptive-metadata writer needed for favorites and richer browse metadata.
4. Add optional hosted/local AI provider adapter(s) behind the existing provider seam.
5. Add CI/schema/test automation.

## Decisions already made

- Human key feel is not a core purchasing criterion.
- Documented MIDI receive is mandatory for recommended hardware.
- The Pi owns the master clock for locally connected devices.
- Playback is local-first; cloud storage is for backup/recovery, not live timing.
- Multi-device routing and device latency compensation are first-class.
- AI interprets intent but never directly emits MIDI.
- Core playback works without AI or Internet access.
- Deterministic MIDI facts, curated metadata, and AI inference remain separate data classes.
- Catalog SQLite is rebuildable; listening history is durable runtime state.
- Unknown model fields fail closed at the `PlaybackIntent` boundary.
- The backend owns queue/playback state; clients reconcile to it over REST/WebSocket.
- Browser progress interpolation anchors at local message receipt time, not server wall-clock subtraction.
- Arbitrary imported SysEx is not executable by default.

## Immediate proof-of-concept tests when hardware arrives

1. Confirm Linux enumerates each USB MIDI device.
2. Send the synthetic single-note fixture and confirm internal audio playback.
3. Verify velocity response and sustain CC64.
4. Verify Program Change / Bank Select behavior.
5. Play the generated GM multichannel fixture and verify channel 10 percussion.
6. Exercise receive range and practical 16/32/48/64-note voice stress.
7. Run long-duration continuous playback and restart/recovery tests.
8. With both keyboards, route the generated two-piano fixture from one master timeline.
9. Measure relative MIDI-to-audio latency and configure route compensation.
10. Exercise the Music Concierge → Smart Station → queue → playback → history loop against real catalog material.
