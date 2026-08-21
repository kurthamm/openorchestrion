# Supported / Candidate Hardware

This table distinguishes documentation evidence from physical project validation.

| Device | MIDI receive | USB | GM / multitimbral | Polyphony | Status | Project view |
| --- | --- | --- | --- | ---: | --- | --- |
| **Casio CT-X700** | Yes, manufacturer documented | Class-compliant USB MIDI | GM Level 1 / multi-part | 48 max | Documented compatible | **Reference candidate** |
| Yamaha PSR-EW310 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Strong second-engine choice |
| Yamaha PSR-EW300 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Strong value choice |
| Yamaha PSR-E363 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Similar engine class to EW300; key count irrelevant here |
| Yamaha YPG-235 | Yes, USB MIDI playback documented | USB MIDI | MIDI/GM-family support | 32 | Candidate | Stronger integrated speakers; lower polyphony |
| Casio WK-245 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Good low-cost fallback |
| Casio WK-220 / WK-200 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Older but useful if inexpensive |
| Casio CTK-3500 | Yes | USB MIDI | GM Level 1 | 48 | Candidate | Cheap development engine if verified working |
| Casio CDP-100 | Yes, 5-pin MIDI IN | DIN MIDI | multitimbral receive | 32 | Candidate | Old piano engine; useful only if very inexpensive |
| Roland EM-10 | Yes | DIN MIDI | GM/GS-family | 24 | Not preferred | Polyphony too restrictive |
| Original Alesis Recital | Inbound behavior not documented to project standard | USB | limited | 128 nominal | **Not recommended** | Do not base project on undocumented MIDI receive |
| Casio CTK-2500 / CTK-2550 | Not suitable for required architecture | — | — | — | **Not recommended** | Wrong connectivity model for this project |

## Evidence policy

A device progresses through three levels:

1. **Documented compatible** — manufacturer documentation supports the required inbound MIDI path.
2. **Community tested** — a contributor verifies playback on physical hardware.
3. **Project validated** — reproduced in the OpenOrchestrion reference build with acceptance tests.

A USB connector alone is not evidence of inbound MIDI playback support.

## Reference acceptance test

A device should not be marked Project Validated until it passes:

- Linux enumeration.
- Note receive/audio output.
- Velocity.
- Sustain CC64.
- Program Change / Bank Select where supported.
- Multichannel playback where claimed.
- Channel 10 percussion where applicable.
- Long-running playback.
- Power-cycle/reconnect behavior.
