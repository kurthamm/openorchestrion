# Test Strategy

## Principle

OpenOrchestrion should not rely on “it seemed to play a song” as hardware or software validation. The project needs deterministic, copyright-clean test material that exercises individual MIDI behaviors and can be reproduced by contributors.

## Synthetic MIDI conformance suite

The repository should generate its own tiny Standard MIDI Files for testing. A generator script is preferable to committing opaque binary fixtures wherever practical.

Planned fixtures:

### 1. `single-note`

- one Note On
- one Note Off
- known pitch and duration

Validates the absolute minimum host → MIDI engine → audio path.

### 2. `velocity-ladder`

Play the same pitch at several velocities, for example 20, 45, 70, 95, 120.

Validates received velocity and gives an audible sanity check for dynamic response.

### 3. `sustain-cc64`

- play chord
- pedal down (CC64)
- release keys
- pedal up

Validates sustain behavior and Stop/Panic cleanup.

### 4. `program-change`

Sequentially request known GM programs and play the same short phrase.

Validates Program Change and, where applicable, Bank Select/profile mapping.

### 5. `gm-ensemble`

Known multichannel arrangement containing, for example:

- piano
- bass
- strings
- brass/woodwind
- channel 10 percussion

Validates multitimbral receive and GM percussion conventions.

### 6. `note-range`

Send notes beyond the instrument's physical keybed to verify the internal sound generator's actual receive range. This is particularly important to OpenOrchestrion because physical key count is not a core procurement criterion.

### 7. `polyphony-stress`

Generate increasingly dense sustained chords and overlapping parts. Measure or audibly characterize voice stealing at different loads.

This does not prove a manufacturer's nominal polyphony number; it measures useful behavior in the target arrangement style.

### 8. `two-piano-split`

Two clearly distinguishable parts routed independently to Device A and Device B.

Validates routing, simultaneous output, Stop/Panic fan-out, and initial synchronization.

### 9. `sync-click`

Send simultaneous short percussive notes to both devices. Record the acoustic result when measuring relative MIDI-to-audio latency.

### 10. `long-run`

A deterministic generated sequence designed to run for hours without copyrighted content.

Validates resource stability, queue progression, reconnect handling, and absence of accumulated stuck notes.

### 11. `unsupported-events`

Include safely ignored metadata and selected unsupported/noncritical MIDI events so the parser can prove it does not crash or execute embedded content.

## Hardware validation levels

### Documented compatible

Manufacturer documentation demonstrates the required inbound MIDI behavior.

### Community tested

A contributor reports physical hardware results and environment details.

### Project validated

The reference project reproduces the conformance suite and records results.

## CT-X700 reference validation

For the reference candidate, record:

- Pi model / OS version
- USB endpoint name and IDs if available
- direct USB connection/topology
- power supply used
- firmware/version information if exposed
- Note On/Off
- velocity
- sustain
- Program Change
- Bank Select behavior
- GM ensemble playback
- channel 10 drums
- note receive range
- polyphony stress observations
- reconnect behavior
- power-cycle recovery
- long-run result
- measured relative/absolute latency where practical

## Timing benchmark

Python/Mido/python-rtmidi is the initial software direction, but timing quality must be measured rather than assumed.

Benchmark under realistic appliance load:

- FastAPI running
- Chromium kiosk running
- WebSocket clients connected
- library database active
- one MIDI device
- two MIDI devices

Capture scheduling jitter and drift over long passages. If Python user-space scheduling cannot meet musical requirements, evaluate ALSA sequencer timestamped events or a dedicated real-time playback helper while keeping the higher-level architecture unchanged.

## Two-device synchronization

Test both electronic and acoustic timing.

Electronic timing:

1. schedule identical events at the same master timestamp;
2. measure each engine's MIDI-to-audio response;
3. store relative device offsets;
4. repeat after power cycles to test stability.

Acoustic timing:

Account for physical distance between speakers and the listening position. Room placement may create a larger audible offset than USB scheduling.

## AI tests

AI tests should never require attached MIDI hardware.

Test:

- prompt → valid PlaybackIntent
- conversational refinement
- schema rejection of invented fields
- hard exclusions preserved
- unavailable-library content not fabricated
- provider failure fallback
- AI never gains a direct MIDI handle

Use deterministic fake providers in CI.

## Library tests

Use generated/open fixtures to test:

- duration calculation
- tempo changes
- channel/program detection
- sustain/controller detection
- percussion detection
- peak-polyphony estimation
- rights/provenance metadata validation
- duplicate detection strategy
- rebuild of SQLite from durable metadata

## Appliance tests

- clean boot reaches service automatically
- kiosk launches when configured
- headless mode works with no display
- phone and kiosk remain state-synchronized
- browser closure does not stop playback
- Internet loss does not stop local playback
- AI outage does not stop manual playback
- MIDI unplug produces safe behavior
- restore drill succeeds on blank storage

## CI direction

Before hardware is available, GitHub Actions can still run:

- unit tests
- schema validation
- linting
- MIDI fixture generation/parser tests
- station-selection tests
- AI fake-provider tests

Physical MIDI/audio validation remains a documented manual/hardware-in-the-loop stage.
