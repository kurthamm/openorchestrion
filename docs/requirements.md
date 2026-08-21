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

### AI Music Concierge

- **FR-020** The system shall provide a natural-language prompt for music requests.
- **FR-021** The AI layer shall translate natural-language requests into a structured `PlaybackIntent`.
- **FR-022** The AI layer shall support conversational refinement of the current intent (for example “more upbeat” or “more piano”).
- **FR-023** AI output shall be schema-validated before it can affect playback.
- **FR-024** The AI layer shall not directly send MIDI messages to hardware.
- **FR-025** The core system shall remain usable when AI is disabled or unavailable.
- **FR-026** The system should support pluggable hosted or local AI providers.
- **FR-027** AI-assisted library enrichment shall distinguish inferred descriptive metadata from deterministic MIDI facts.

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

### Device management

- **FR-060** The system shall discover available MIDI outputs on Linux.
- **FR-061** Recommended hardware profiles shall require documented or physically verified inbound MIDI behavior.
- **FR-062** Device profiles shall record relevant capabilities such as polyphony, multitimbral support, note receive range, controllers, program mapping, and latency offset.
- **FR-063** Device-specific behavior shall be isolated behind profiles/adapters rather than hard-coded throughout the application.
- **FR-064** The system shall detect loss of a MIDI endpoint and enter a safe state or apply configured fallback routing.

### Multi-device / two-piano

- **FR-080** A single host shall be able to drive at least two MIDI outputs from one master timeline.
- **FR-081** The router shall be able to map tracks/channels to specific devices.
- **FR-082** Device profiles shall support configurable latency compensation.
- **FR-083** The system shall support `TWO_PIANO` performances with independent Piano I and Piano II destinations.
- **FR-084** The system shall support separated `PIANO_DUET` material when the MIDI structure permits it.
- **FR-085** The system shall support purpose-built `DUELING_PIANO` routing/arrangements.
- **FR-086** The routing engine should support instrument-family preferences and polyphony-load distribution.

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

### Backup / recovery

- **FR-120** The system shall support off-device backup of music, metadata, stations/playlists, configuration, and database state.
- **FR-121** Backup storage may use a cloud provider such as Google Drive but shall not be required for live playback.
- **FR-122** The project shall document a bare-metal recovery procedure.
- **FR-123** A full-system image or reproducible deployment shall be maintained as a second recovery layer.

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

### AI Concierge MVP

1. “Play dinner music for an hour” produces a valid structured intent and matching queue.
2. “More upbeat” modifies the active intent rather than discarding it.
3. “Popular Christmas music” weights holiday and familiarity metadata appropriately.
4. Malformed/model-hallucinated fields are rejected by schema validation.
5. AI provider outage leaves manual browsing/stations functional.

### Two-device MVP

1. Both devices follow one master playback timeline.
2. Tracks can be explicitly routed to different outputs.
3. Configured per-device offsets change event scheduling predictably.
4. A two-piano MIDI performance can route Piano I and Piano II independently.
5. Device removal triggers configured safe/fallback behavior.
