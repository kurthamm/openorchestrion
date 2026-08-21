# Roadmap

## Phase 0: Hardware proof

- Acquire a documented MIDI-receiving keyboard or sound engine.
- Verify Pi/Linux to keyboard MIDI playback.
- Verify internal speaker output, velocity, sustain, Program Change, GM parts, and drums.
- Record device identity and capabilities in a reusable profile.

## Phase 1: Single-device appliance

- FastAPI service.
- MIDI device discovery.
- Standard MIDI File playback.
- Play / pause / stop / skip.
- Panic / all-notes-off.
- Queue management.
- Local responsive web UI.
- Now Playing state.
- Chromium kiosk startup.
- SQLite library index.
- File-system scanner.
- Basic metadata and favorites.

## Phase 2: AI Music Concierge

- Natural-language prompt control.
- Provider-neutral AI adapter.
- `PlaybackIntent` schema and validation.
- Conversational refinement of an active station/queue.
- Requests such as dinner music, popular Christmas, relaxing classical, more upbeat, more recognizable, more piano, etc.
- Deterministic fallback when AI is disabled.
- No direct AI-to-MIDI execution path.

## Phase 3: Library intelligence

- MIDI structural analyzer.
- Duration calculation.
- Track/channel analysis.
- Program and percussion detection.
- Sustain/controller detection.
- Estimated peak-polyphony analysis.
- Compatibility scoring.
- Genre, mood, theme, era, familiarity and source metadata.
- AI-assisted metadata enrichment with provenance markers.
- Play history and no-repeat rules.
- Smart stations and weighted discovery.

## Phase 4: Multi-instrument / GM refinement

- Preserve MIDI channel separation.
- Bank Select and Program Change policy.
- Device program maps.
- GM fallback behavior.
- Original Arrangement mode.
- Piano Only rendering mode.
- User-selectable instrument overrides.

## Phase 5: Two sound engines

- Multiple simultaneous MIDI output ports.
- Track/channel routing rules.
- Per-device latency offsets.
- Device capability-aware routing.
- Polyphony-load distribution.
- Preferred-engine mapping by instrument family.
- True `TWO_PIANO` routing.
- `PIANO_DUET` routing.
- Purpose-built `DUELING_PIANO` arrangements.

## Phase 6: Appliance polish

- Touchscreen-first layout.
- PWA behavior for phones/tablets.
- Local discovery / friendly hostname.
- systemd service packaging.
- Setup wizard.
- Backup and restore UI.
- Library sync status.
- Health dashboard.
- Graceful device-disconnect behavior.

## Phase 7: Distributed OpenOrchestrion

- Lightweight remote MIDI endpoints.
- Pre-stage/cached MIDI files on endpoints.
- Clock synchronization.
- Coordinated start timestamps.
- Room/device groups.
- Multi-room playback.
- Fallback routing when an endpoint is unavailable.

## Publication milestones

- Public architecture and requirements.
- Supported-hardware matrix.
- First successful CT-X700 or equivalent demo.
- Video showing natural-language request to hardware playback.
- Two-device synchronized demo.
- Dueling-piano / two-piano demo.
- Reproducible Raspberry Pi installation guide.
