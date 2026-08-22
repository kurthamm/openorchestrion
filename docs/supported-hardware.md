# Supported / Candidate Hardware

This table distinguishes documentation evidence from physical project validation.

| Device | MIDI receive | USB | GM / multitimbral | Polyphony | Status | Project view |
| --- | --- | --- | --- | ---: | --- | --- |
| **Casio CTK-6200** | Yes, manufacturer documented computer/MIDI send and receive | USB MIDI | GM Level 1 / multichannel arranger architecture | 48 max | **Documented compatible** | **Current primary acquisition target** |
| **Yamaha PSR-EW300** | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | **Documented compatible** | **Current complementary acquisition target** |
| Casio CT-X700 | Yes, manufacturer documented | Class-compliant USB MIDI | GM Level 1 / multi-part | 48 max | **Documented compatible** | Prior reference candidate / useful fallback |
| Yamaha PSR-EW310 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Strong alternative Yamaha engine |
| Yamaha PSR-E363 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Similar engine class to EW300; key count irrelevant here |
| Casio WK-500 | Yes, computer-to-keyboard MIDI playback documented | USB MIDI | GM Level 1 / multichannel | 48 | Candidate | Strong alternate Casio ensemble engine |
| Yamaha YPG-235 | Yes, USB MIDI playback documented | USB MIDI | MIDI/GM-family support | 32 | Candidate | Stronger integrated speakers; lower polyphony |
| Casio WK-245 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Good low-cost fallback |
| Casio WK-220 / WK-200 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Older but useful if inexpensive |
| Casio CTK-4400 | Yes | USB MIDI | GM Level 1 | 48 | Candidate | Useful lower-cost Casio fallback |
| Casio CTK-3500 | Yes | USB MIDI | GM Level 1 | 48 | Candidate | Cheap development engine if verified working |
| Casio CDP-100 | Yes, 5-pin MIDI IN | DIN MIDI | multitimbral receive | 32 | Candidate | Old piano engine; useful only if very inexpensive |
| Roland EM-10 | Yes | DIN MIDI | GM/GS-family | 24 | Not preferred | Polyphony too restrictive |
| Original Alesis Recital | Inbound behavior not documented to project standard | USB | limited | 128 nominal | **Not recommended** | Do not base project on undocumented MIDI receive |
| Casio CTK-2500 / CTK-2550 | Not suitable for required architecture | — | — | — | **Not recommended** | Wrong connectivity model for this project |

## Current target pairing

The current intended first two-engine build is:

```text
OpenOrchestrion Pi
      │
      ├── Casio CTK-6200
      │     primary/general ensemble engine
      │     48-note nominal polyphony
      │     GM-capable Casio sound set
      │
      └── Yamaha PSR-EW300
            complementary Yamaha engine
            48-note nominal polyphony
            GM/XGlite-family sound set
```

This pairing is preferred because both devices are broad general-purpose sound engines, while their different manufacturers provide useful timbral diversity. Neither is being selected for human key feel or physical key count.

If both are acquired, the initial multi-device validation should compare instrument families, practical voice stealing, Program/Bank behavior, relative MIDI-to-audio latency, two-piano routing, and split multichannel arrangements.

## Evidence policy

A device progresses through three levels:

1. **Documented compatible** — manufacturer documentation supports the required inbound MIDI path.
2. **Community tested** — a contributor verifies playback on physical hardware.
3. **Project validated** — reproduced in the OpenOrchestrion reference build with acceptance tests.

A USB connector alone is not evidence of inbound MIDI playback support.

## Existing detailed evidence profile

The earlier CT-X700 investigation produced both narrative and machine-readable profiles and remains useful as a documented fallback/reference example:

- [CT-X700 evidence/profile](hardware/casio-ct-x700.md)
- [`device-profiles/casio-ct-x700.json`](../device-profiles/casio-ct-x700.json)

Detailed CTK-6200 and PSR-EW300 profiles should be added as procurement/physical validation proceeds.

## Reference acceptance test

A device should not be marked Project Validated until it passes:

- Linux enumeration.
- Note receive/audio output.
- Velocity.
- Sustain CC64.
- Program Change / Bank Select where supported.
- Multichannel playback where claimed.
- Channel 10 percussion where applicable.
- Note receive range beyond physical keybed where claimed.
- Practical polyphony stress behavior.
- Long-running playback.
- Power-cycle/reconnect behavior.
- Endpoint identity capture.
- Latency characterization for multi-device use.

See [test-strategy.md](test-strategy.md) for the reusable conformance suite.

## Second-engine strategy

The first complementary engine should ideally come from a different sound family rather than simply duplicating the first. The CTK-6200 + PSR-EW300 target pairing implements that strategy directly: Casio and Yamaha provide two independent synthesis engines, two distinct sound palettes, and a useful platform for true two-piano and split-ensemble experiments.

The objective is tone diversity plus independent synthesis capacity, not human key feel.
