# Supported / Candidate Hardware

This table distinguishes documentation evidence from physical project validation.

| Device | MIDI receive | USB | GM / multitimbral | Polyphony | Status | Project view |
| --- | --- | --- | --- | ---: | --- | --- |
| **Casio WK-220** | Verified on the reference Pi | USB MIDI | Checklist reports multichannel/percussion and program/bank reception | 48 nominal; stress behavior reported | **Reference-tested; scope below** | **Current connected engine** |
| Casio CT-X700 | Yes, manufacturer documented | Class-compliant USB MIDI | GM Level 1 / multi-part | 48 max | **Documented compatible; unavailable** | Future foreground engine in owner-deferred #84 plan |
| Casio CTK-6200 | Manufacturer documented | USB MIDI | GM Level 1 / multichannel | 48 max | Documented compatible | Historical procurement candidate; not the current purchase plan |
| Yamaha PSR-EW300 | Two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Documented compatible | Optional later candidate; not currently acquired |
| Yamaha PSR-EW310 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Strong alternative Yamaha engine |
| Yamaha PSR-E363 | Yes, two-way USB MIDI documented | USB MIDI/audio | GM/XGlite family | 48 | Candidate | Similar engine class to EW300; key count irrelevant here |
| Casio WK-500 | Yes, computer-to-keyboard MIDI playback documented | USB MIDI | GM Level 1 / multichannel | 48 | Candidate | Strong alternate Casio ensemble engine |
| Yamaha YPG-235 | Yes, USB MIDI playback documented | USB MIDI | MIDI/GM-family support | 32 | Candidate | Stronger integrated speakers; lower polyphony |
| Casio WK-245 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Good low-cost fallback |
| Casio WK-200 | Yes | USB MIDI | multitimbral / GM-family | 48 | Candidate | Older but useful if inexpensive |
| Casio CTK-4400 | Yes | USB MIDI | GM Level 1 | 48 | Candidate | Useful lower-cost Casio fallback |
| Casio CTK-3500 | Yes | USB MIDI | GM Level 1 | 48 | Candidate | Cheap development engine if verified working |
| Casio CDP-100 | Yes, 5-pin MIDI IN | DIN MIDI | multitimbral receive | 32 | Candidate | Old piano engine; useful only if very inexpensive |
| Roland EM-10 | Yes | DIN MIDI | GM/GS-family | 24 | Not preferred | Polyphony too restrictive |
| Original Alesis Recital | Inbound behavior not documented to project standard | USB | limited | 128 nominal | **Not recommended** | Do not base project on undocumented MIDI receive |
| Casio CTK-2500 / CTK-2550 | Not suitable for required architecture | — | — | — | **Not recommended** | Wrong connectivity model for this project |

## Current physical baseline

One **Casio WK-220** is connected to the Raspberry Pi. The prior CTK-6200 + PSR-EW300
purchase proposal is historical. The later [two-engine plan](two-engine-orchestration.md)
uses CT-X700 foreground + WK-220 support, but the owner deferred that work until the
new keyboard is available. No delivery date or purchase is assumed.

[Issue #1's WK-220 reports](https://github.com/kurthamm/openorchestrion/issues/1#issuecomment-5564036325)
record the checklist as passed on September 6 at `817e978`, including audible notes,
velocity, sustain, bank/program reception, multichannel/percussion, polyphony stress,
expressive playback and reconnect. The [September 7 release](single-keyboard-release-2026-09.md)
records a loaded 120-minute headless software timing run. These are recorded results
on named builds, not fresh acoustic measurements of each later release.

The generic ALSA name `CASIO USB-MIDI` and USB ID `07cf:6803` do not uniquely identify
this model; Linux may label that identifier CTK-3500. Use the physical device identity
and test report together. WK-220 results do not validate WK-200 or any other Casio.
Receive-range characterization and measured MIDI-to-audio latency remain distinct
from the reported checklist. Two-engine acoustic synchronization is unmeasured.

## Evidence policy

A device progresses through three levels:

1. **Documented compatible** — manufacturer documentation supports the required inbound MIDI path.
2. **Community tested** — a contributor verifies playback on physical hardware.
3. **Project validated** — reproduced in the OpenOrchestrion reference build with acceptance tests.

A USB connector alone is not evidence of inbound MIDI playback support.

## Existing detailed evidence profile

The CT-X700 investigation provides manufacturer evidence for the future plan:

- [CT-X700 evidence/profile](hardware/casio-ct-x700.md)
- [`device-profiles/casio-ct-x700.json`](../device-profiles/casio-ct-x700.json)

Only add other device profiles when the corresponding device is deliberately selected; prior procurement notes are not authorization to purchase or implement them.

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

Generic routing already supports multiple destinations. Device-specific affinity,
manual orchestration UI and acoustic calibration remain under deferred issue #84.
The Yamaha issue #11 is an optional later extension, not an active competing plan.
