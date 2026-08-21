# Requirements Baseline

This document captures the current requirements discussed for OpenOrchestrion. IDs are intentionally stable so future issues and tests can reference them.

## Functional requirements

### Appliance / UI

- **FR-001** The system shall provide a responsive web UI usable from the attached touchscreen and household browsers.
- **FR-002** The attached display shall be able to operate in kiosk mode without exposing ordinary desktop/Linux UI during normal use.
- **FR-003** The UI shall provide play, pause, stop, skip, queue, Now Playing, favorites, and recent-history controls.
- **FR-004** The UI shall support browsing by title, composer/artist, genre, era, mood, theme, performance type, and source.
- **FR-005** The system shall support random/shuffle playback with configurable no-repeat rules.
- **FR-006** The system shall support dynamic stations such as dinner music, ragtime, relaxing classical, Christmas, cocktail jazz, and two-piano repertoire.
- **FR-007** Multiple connected clients shall receive synchronized playback state updates.
- **FR-008** The system shall support both an attached-display Appliance Edition and a display-free Headless Edition using the same server and web application.
- **FR-009** The attached display shall not require a separate native GUI application or separately maintained front-end codebase.
- **FR-010** The reference Appliance Edition shall target a 7-inch-class touchscreen suitable for the Music Concierge, Now Playing, queue, station shortcuts, and touch transport controls.
- **FR-011** The local appliance UI shall prioritize immediate listening functions over administration complexity.
- **FR-012** Full administration functions shall remain available through the household web UI, including library import, metadata editing, device profiles, routing, latency calibration, AI configuration, backup, logs, and diagnostics.
- **FR-013** Loss or absence of the attached display shall not prevent playback or remote browser control.
- **FR-014** The system should support installation as a PWA or equivalent app-like browser experience on phones/tablets.
- **FR-015** The system should support friendly local discovery/name resolution such as `openorchestrion.local` where the deployment environment permits it.
- **FR-016** A future guest-request mode should provide a limited song-request interface without exposing administrative configuration.
- **FR-017** Optional physical appliance controls such as Play/Pause, Stop/Panic, or a rotary encoder shall invoke the same server command/state layer as web clients.

### AI Music Concierge

- **FR-020** The system shall provide a natural-language prompt for music requests.
- **FR-021** The AI layer shall translate natural-language requests into a structured `PlaybackIntent`.
- **FR-022** The AI layer shall support conversational refinement of the current intent (for example “more upbeat” or “more piano”).
- **FR-023** AI output shall be schema-validated before it can affect playback.
- **FR-024** The AI layer shall not directly send MIDI messages to hardware.
- **FR-025** The core system shall remain usable when AI is disabled or unavailable.
- **FR-026** The system should support pluggable hosted or local AI providers.
- **FR-027** AI-assisted library enrichment shall distinguish inferred descriptive metadata from deterministic MIDI facts.
- **FR-028** The system should support optional speech-to-text input feeding the same natural-language Music Concierge path.
- **FR-029** AI/selection logic shall not fabricate tracks that are not present in the indexed library.
- **FR-030** When soft preferences must be relaxed to produce a usable queue, the system should retain/expose the resulting interpretation or relaxation for diagnostics and optional user explanation.
- **FR-031** AI-generated metadata shall retain provenance sufficient to distinguish the provider/model and confidence or review state from curated metadata.

### MIDI playback

- **FR-040** The system shall play Standard MIDI Files through one or more external MIDI sound engines.
- **FR-041** Playback shall preserve timing, note velocity, and relevant controller events.
- **FR-042** The system shall support sustain CC64.
- **FR-043** The system shall preserve Program Change and Bank Select where compatible with the target profile.
- **FR-044** The system shall support multichannel/multitimbral arrangements.
- **FR-045** The system shall support General MIDI percussion/channel conventions where supported by the target device.
- **FR-046** The system shall provide a panic/all-notes-off function.
- **FR-047** The system shall support pause/resume and queue transitions without leaving stuck notes.
- **FR-048** The system should support tempo adjustment and transpose when safe/appropriate.
- **FR-049** The system shall support an Original Arrangement rendering path that preserves compatible channel/program intent.
- **FR-050** The system should support a Piano Only rendering mode when the source structure can be safely mapped to piano.

### Device management

- **FR-060** The system shall discover available MIDI outputs on Linux.
- **FR-061** Recommended hardware profiles shall require documented or physically verified inbound MIDI behavior.
- **FR-062** Device profiles shall record relevant capabilities such as polyphony, multitimbral support, note receive range, controllers, program mapping, and latency offset.
- **FR-063** Device-specific behavior shall be isolated behind profiles/adapters rather than hard-coded throughout the application.
- **FR-064** The system shall detect loss of a MIDI endpoint and enter a safe state or apply configured fallback routing.
- **FR-065** Hardware compatibility status shall distinguish at least `documented`, `community-tested`, and `project-validated` evidence levels.
- **FR-066** Device profiles should retain manufacturer documentation references that substantiate claimed capabilities.
- **FR-067** The reference validation process shall record stable USB/MIDI endpoint identity information where available.

### Multi-device / two-piano

- **FR-080** A single host shall be able to drive at least two MIDI outputs from one master timeline.
- **FR-081** The router shall be able to map tracks/channels to specific devices.
- **FR-082** Device profiles shall support configurable latency compensation.
- **FR-083** The system shall support `TWO_PIANO` performances with independent Piano I and Piano II destinations.
- **FR-084** The system shall support separated `PIANO_DUET` material when the MIDI structure permits it.
- **FR-085** The system shall support purpose-built `DUELING_PIANO` routing/arrangements.
- **FR-086** The routing engine should support instrument-family preferences and polyphony-load distribution.
- **FR-087** The project shall document a repeatable two-device latency calibration procedure.
- **FR-088** Stop/Panic shall fan out safely to every active MIDI destination.
- **FR-089** A multi-device performance profile shall define behavior when one destination becomes unavailable (stop, reduced instrumentation, or compatible fallback routing).
- **FR-090** Future distributed endpoints shall pre-stage MIDI assets and schedule local playback from a coordinated future start rather than relying on per-event delivery over ordinary Wi-Fi.

### Library

- **FR-100** The system shall index local `.mid` files into a searchable catalog.
- **FR-101** Each asset shall retain title, source, and rights/provenance status.
- **FR-102** The catalog shall support genre, mood, theme, era, performance type, familiarity, quality, and user tags.
- **FR-103** The importer shall determine duration, tracks, channels, programs, percussion, controllers, and note range deterministically.
- **FR-104** The importer should estimate peak simultaneous voices/polyphony demand.
- **FR-105** The library shall track favorites, play count, and last-played history.
- **FR-106** The library shall distinguish Verified/Open material from Personal imports.
- **FR-107** SQLite shall be treated as an operational/search index; durable library metadata shall be recoverable outside a single database file.
- **FR-108** The system should support quality grading of MIDI performances.
- **FR-109** Smart stations shall support deterministic weighting/rules including no-repeat windows, composer/artist diversity, history weighting, quality preference, and optional duration/energy constraints.
- **FR-110** The station engine should be able to record diagnostic selection reasons/scores for a queued track.
- **FR-111** A track merely queued shall not automatically count as played for history/no-repeat purposes.
- **FR-112** The importer shall distinguish objective MIDI facts from curated or AI-inferred descriptive metadata.
- **FR-113** The public project shall support a copyright-clean synthetic MIDI conformance library independent of copyrighted musical repertoire.
- **FR-114** Two-piano/duet assets shall be able to record part-to-track/channel mapping and preferred device roles.

### Backup / recovery

- **FR-120** The system shall support off-device backup of music, metadata, stations/playlists, configuration, and database state.
- **FR-121** Backup storage may use a cloud provider such as Google Drive but shall not be required for live playback.
- **FR-122** The project shall document a bare-metal recovery procedure.
- **FR-123** A full-system image or reproducible deployment shall be maintained as a second recovery layer.
- **FR-124** Backup/synchronization shall not mount a remote cloud database as the time-critical live playback data path.
- **FR-125** Release/recovery documentation should include a tested restore drill onto blank replacement storage.

## Non-functional requirements

- **NFR-001 Local-first:** Active playback shall not require Internet access.
- **NFR-002 Timing:** Time-critical MIDI scheduling shall execute locally on the playback host.
- **NFR-003 Appliance behavior:** Services shall start automatically after boot and recover to a known safe state.
- **NFR-004 Reliability:** Long-duration unattended playback shall not accumulate stuck notes or unbounded resource growth.
- **NFR-005 Security:** The default deployment shall be intended for a trusted LAN and shall not expose management interfaces publicly by default.
- **NFR-006 Secrets:** AI/cloud credentials shall never be stored in source control or exposed to browser clients unnecessarily.
- **NFR-007 Extensibility:** Core architecture shall not depend on the Casio CT-X700 specifically.
- **NFR-008 Portability:** The initial target is Raspberry Pi OS/Linux, but interfaces should avoid unnecessary Pi-specific coupling.
- **NFR-009 Reproducibility:** Another builder should be able to reproduce the system from public documentation and supported hardware.
- **NFR-010 Rights hygiene:** The public repository shall not redistribute MIDI whose rights are unclear merely because it is downloadable elsewhere.
- **NFR-011 Accessibility:** The web UI should be usable with standard browser accessibility mechanisms and touch targets appropriate for kiosk use.
- **NFR-012 Observability:** Device, library, playback, backup, and AI-provider health should be visible in an administrative status view.
- **NFR-013 Resource efficiency:** The initial reference appliance shall be designed to run comfortably on a Raspberry Pi 5 with 4 GB RAM without requiring a larger-memory model for ordinary hosted-AI operation.
- **NFR-014 UI maintainability:** Attached-display and remote-browser experiences shall share the same responsive application and API contracts.
- **NFR-015 Testability:** Core MIDI behavior shall be testable with generated/copyright-clean fixtures rather than requiring commercial music files.
- **NFR-016 Evidence:** Hardware compatibility claims shall be traceable to manufacturer documentation or reproducible physical test evidence.
- **NFR-017 Timing evidence:** The chosen Linux/Python MIDI scheduling path shall be benchmarked under realistic appliance load before being treated as musically sufficient.
- **NFR-018 Determinism boundary:** AI may influence intent/metadata but time-critical MIDI scheduling and hardware execution shall remain deterministic.

## Reference hardware baseline

The initial reproducible Appliance Edition is documented in `docs/reference-build.md` and currently targets:

- Raspberry Pi 5, 4 GB
- 7-inch-class attached touchscreen
- active cooling
- reliable Pi 5 power supply
- 128 GB high-endurance microSD initially, with NVMe as an optional upgrade
- Raspberry Pi OS 64-bit
- Chromium kiosk mode for the local display
- direct USB MIDI where supported

This baseline is intentionally separate from the MIDI sound-engine profile. OpenOrchestrion remains portable to comparable Linux hardware.

## Reference acceptance tests

### Single-device MVP

1. Fresh boot reaches appliance UI without manual shell interaction.
2. Host discovers the configured MIDI device.
3. Browser request starts a local MIDI file and audible sound is generated by the hardware engine.
4. Velocity differences are audible/observable.
5. Sustain CC64 is honored.
6. Program changes select expected sounds on the reference profile.
7. Multichannel GM file renders multiple parts and percussion.
8. Stop/panic leaves no hanging notes.
9. Phone and touchscreen remain synchronized through playback changes.
10. Internet disconnect during playback does not stop the music.
11. The same deployment remains functional when the attached display is disconnected and control continues from a household browser.
12. Local kiosk and remote browser use the same application/API state rather than independent playback controllers.
13. Notes outside the physical keybed but within the device's documented receive range are tested.
14. Long-duration playback completes without resource growth or stuck-note accumulation.

### AI Concierge MVP

1. “Play dinner music for an hour” produces a valid structured intent and matching queue.
2. “More upbeat” modifies the active intent rather than discarding it.
3. “Popular Christmas music” weights holiday and familiarity metadata appropriately.
4. Malformed/model-hallucinated fields are rejected by schema validation.
5. AI provider outage leaves manual browsing/stations functional.
6. A request for unavailable content does not cause fabricated tracks to appear.
7. Speech input, if enabled, enters through the same validated intent path as typed text.

### Two-device MVP

1. Both devices follow one master playback timeline.
2. Tracks can be explicitly routed to different outputs.
3. Configured per-device offsets change event scheduling predictably.
4. A two-piano MIDI performance can route Piano I and Piano II independently.
5. Device removal triggers configured safe/fallback behavior.
6. Stop/Panic reaches both destinations.
7. A repeatable synchronization fixture is used to measure relative audio latency.

### Recovery MVP

1. Provision blank replacement storage.
2. Reinstall/restore OpenOrchestrion without relying on the failed device.
3. Restore music, metadata, stations/playlists, configuration, and runtime database state.
4. Reconnect hardware using device profiles.
5. Confirm library, AI configuration, and playback functionality.
