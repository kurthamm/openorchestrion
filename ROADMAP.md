# Roadmap

## Phase 0: Hardware proof and conformance harness

- Acquire a documented MIDI-receiving keyboard or sound engine.
- Verify Pi/Linux to keyboard MIDI playback.
- Verify internal speaker output, velocity, sustain, Program Change, GM parts, and drums.
- Record device identity and capabilities in a reusable profile.
- Build copyright-clean synthetic MIDI conformance fixtures.
- Verify notes outside the physical keybed when the device claims a wider MIDI receive range.
- Stress-test practical polyphony/voice stealing.
- Benchmark MIDI scheduling jitter/drift under realistic Pi appliance load.
- Add CI for unit tests, linting, schema validation, and generated MIDI fixture tests.

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
- Headless mode using the same application.
- SQLite library index.
- File-system scanner.
- Basic metadata and favorites.
- Friendly local discovery such as `openorchestrion.local` where supported.

## Phase 2: AI Music Concierge

- Natural-language prompt control.
- Provider-neutral AI adapter.
- `PlaybackIntent` schema and validation.
- Conversational refinement of an active station/queue.
- Requests such as dinner music, popular Christmas, relaxing classical, more upbeat, more recognizable, more piano, etc.
- Deterministic fallback when AI is disabled.
- No direct AI-to-MIDI execution path.
- Explicit handling when requested content does not exist in the library.
- Optional speech-to-text front end using the same validated intent path.

## Phase 3: Library intelligence and smart stations

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
- Composer/artist diversity rules.
- Rarely-played/discovery weighting.
- Selection diagnostics/explanations.
- Durable sidecar/exportable metadata sufficient to rebuild SQLite.

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
- Repeatable acoustic/electronic latency calibration procedure.
- Device capability-aware routing.
- Polyphony-load distribution.
- Preferred-engine mapping by instrument family.
- True `TWO_PIANO` routing.
- `PIANO_DUET` routing.
- Purpose-built `DUELING_PIANO` arrangements.
- Device-loss behavior per performance profile.

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
- Optional physical controls (Play/Pause, Stop/Panic, rotary encoder).
- Optional limited guest/QR song-request mode.
- Enclosure/reference physical build files and BOM.

## Phase 7: Distributed OpenOrchestrion

- Lightweight remote MIDI endpoints.
- Pre-stage/cached MIDI files on endpoints.
- Clock synchronization.
- Coordinated start timestamps.
- Room/device groups.
- Multi-room playback.
- Fallback routing when an endpoint is unavailable.
- Optional spatial/antiphonal arrangement profiles.

## Future experiments

- Home Assistant/local automation API integration.
- AI Librarian enrichment/duplicate assistance.
- AI/rule-based arranger for Piano Only and multi-device transformations.
- Software-synth destination/fallback profile.
- Local AI deployment profile with separately documented compute requirements.

## Publication milestones

- Public architecture and requirements.
- Architecture Decision Records.
- Supported-hardware matrix and manufacturer-evidence profiles.
- First successful CT-X700 or equivalent demo.
- Video showing natural-language request to hardware playback.
- Two-device synchronized demo.
- True two-piano demo.
- Dueling-piano demo.
- Reproducible Raspberry Pi installation guide.
- Verified-open starter MIDI catalog/index.
- Updated OpenOrchestrion-branded white paper.
- GitHub Pages/project site with photos/video and build guide.
