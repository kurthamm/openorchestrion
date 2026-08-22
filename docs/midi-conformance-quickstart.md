# MIDI Conformance Quickstart

OpenOrchestrion includes a generated, copyright-clean MIDI test laboratory. Use it before testing downloaded repertoire so software behavior and hardware behavior can be isolated.

## Generate the suite

After installing the project in editable mode:

```bash
python -m pip install -e ".[dev]"
openorchestrion-fixtures build/midi-fixtures
```

The generator writes 14 Standard MIDI Files and a machine-readable `manifest.json`.

## Fast first-hardware sequence

When a new MIDI sound engine is connected, use this order:

1. `single-note.mid` — prove host-to-device playback.
2. `velocity-ladder.mid` — verify dynamic response.
3. `sustain-cc64.mid` — verify pedal/controller receive.
4. `program-change.mid` — verify GM program and bank behavior.
5. `gm-ensemble.mid` — verify multitimbral playback and channel 10 percussion.
6. `note-range.mid` — test MIDI notes outside the physical keybed.
7. `polyphony-16/32/48/64.mid` — characterize voice stealing.
8. `two-piano-split.mid` — verify channel/track routing to two devices.
9. `sync-click.mid` — measure relative device latency.
10. `long-run.mid` — stability/endurance test.

`unsupported-events.mid` is primarily a parser/importer-resilience fixture and should not be used as the first hardware playback test.

## Short development suite

The long-run fixture defaults to a logical two-hour sequence. For quick development runs:

```bash
openorchestrion-fixtures build/midi-fixtures --long-run-minutes 1
```

## Why generate instead of commit binaries?

The source code defines the expected MIDI events, so contributors can audit exactly what a test sends. The binary files can be regenerated identically enough for behavioral testing, and the repository does not need to carry opaque test music.

## Expected output

```text
build/midi-fixtures/
├── single-note.mid
├── velocity-ladder.mid
├── sustain-cc64.mid
├── program-change.mid
├── gm-ensemble.mid
├── note-range.mid
├── polyphony-16.mid
├── polyphony-32.mid
├── polyphony-48.mid
├── polyphony-64.mid
├── two-piano-split.mid
├── sync-click.mid
├── long-run.mid
├── unsupported-events.mid
└── manifest.json
```

The generated `manifest.json` records the purpose and expected characteristics of each fixture so future analyzers and hardware-validation tools can consume the same contract.
