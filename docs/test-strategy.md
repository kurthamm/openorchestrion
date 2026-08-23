# Test Strategy

## Principle

OpenOrchestrion should not rely on “it seemed to play a song” as hardware or software validation. The project needs deterministic, copyright-clean test material that exercises individual MIDI behaviors and can be reproduced by contributors.

## Current implementation

The first synthetic conformance generator is implemented in:

`openorchestrion.testing.midi_fixtures`

After installing the project, generate the complete suite with:

```bash
openorchestrion-fixtures build/midi-fixtures
```

or directly from Python:

```bash
python -m openorchestrion.testing.midi_fixtures build/midi-fixtures
```

The default suite creates **14 MIDI files plus `manifest.json`**:

```text
single-note.mid
velocity-ladder.mid
sustain-cc64.mid
program-change.mid
gm-ensemble.mid
note-range.mid
polyphony-16.mid
polyphony-32.mid
polyphony-48.mid
polyphony-64.mid
two-piano-split.mid
sync-click.mid
long-run.mid
unsupported-events.mid
manifest.json
```

`long-run.mid` represents 120 minutes by default. A shorter or longer test can be generated with:

```bash
openorchestrion-fixtures build/midi-fixtures --long-run-minutes 240
```

The generated directory is intentionally ignored by Git. The source generator and assertions are versioned; binary output is reproducible. Unit tests verify the expected velocities, sustain values, GM channels/percussion, full MIDI note range, simultaneous polyphony loads, independent two-piano channels, synchronized click timestamps, and parser-safe noncritical event content.

## Rights in the generated fixtures

The MIDI files this generator produces are **offered under the project's MIT
license**, the same terms as the repository itself (see `LICENSE`). This is an
explicit grant covering the generated output, not an inference from the licence
of the generator's source code.

They contain no third-party composition: every note is written by
`openorchestrion.testing.midi_fixtures`, so no separate composition-level
permission is involved. That makes the suite the one body of content this
project can clear from first principles, and it is imported under a real rights
record — `SUITE_RIGHTS` in that module — which the repository contract check
audits like any other claim. MIT permits redistribution provided the copyright
notice travels with the files, so the record carries the attribution text and is
classified `permitted-with-attribution` rather than `permitted`.

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

The initial fixture deliberately avoids sending arbitrary SysEx to hardware. SysEx parsing can be tested separately without making an unknown device execute vendor-specific commands.

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
