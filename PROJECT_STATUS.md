# Project Status

## Phase

**Architecture / hardware validation / repository bootstrap**

OpenOrchestrion has a detailed design baseline but the first end-to-end physical build is still pending.

## Current reference device

**Casio CT-X700** is the leading first-device candidate because manufacturer documentation explicitly supports computer-to-keyboard MIDI playback. Relevant capabilities include USB MIDI, General MIDI Level 1, multi-part receive, Program Change/Bank Select, velocity, sustain/controllers, AiX sound generation, 600 tones, 48-note maximum polyphony, and built-in speakers.

**Status:** documented compatible; physical project validation pending.

## Secondary-device candidates

A second Yamaha engine is strategically attractive because it complements the Casio sound palette rather than merely duplicating it. Candidates identified so far:

1. Yamaha PSR-EW310
2. Yamaha PSR-EW300
3. Yamaha PSR-E363
4. Yamaha YPG-235 (lower polyphony but stronger integrated speakers)

## Decisions already made

- Human key feel is not a core purchasing criterion.
- Documented MIDI receive is mandatory for recommended hardware.
- The Pi owns the master clock for locally connected devices.
- Playback is local-first; cloud storage is for backup/recovery, not live timing.
- The library stores provenance and rights metadata.
- Multi-device routing is first-class even if v1 uses one device.
- Device-specific latency compensation is part of the routing model.
- Natural-language music selection is a core feature via the AI Music Concierge.
- AI interprets intent but does not directly emit MIDI.
- Core playback must work without AI or Internet access.

## Immediate proof-of-concept tests

1. Confirm Linux enumerates the USB MIDI device.
2. Send one note from Linux to the keyboard and confirm internal audio playback.
3. Verify velocity response.
4. Verify sustain (CC64).
5. Verify Program Change / Bank Select behavior.
6. Play a simple GM multichannel file.
7. Verify channel 10 percussion.
8. Play an expressive solo-piano file.
9. Stress test polyphony with sustained dense passages.
10. Run long-duration continuous playback.
11. Power-cycle and verify automatic recovery.
12. If a second keyboard is available, test synchronized split routing and measure relative latency.
13. Exercise the AI Music Concierge against deterministic library results.
