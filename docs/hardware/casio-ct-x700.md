# Casio CT-X700 Reference Profile

## Project role

The Casio CT-X700 is the current **reference sound-engine candidate** for the first OpenOrchestrion physical build. It is attractive because the manufacturer explicitly documents the computer-to-keyboard MIDI path OpenOrchestrion requires.

This document records the evidence behind that decision. It does **not** mark the unit Project Validated; physical Pi/Linux testing is still required.

## Why it fits OpenOrchestrion

OpenOrchestrion needs this direction:

```text
Raspberry Pi / Linux host
          │
          │ USB MIDI
          ▼
      CT-X700
          │
   AiX sound generator
          │
    internal speakers
```

Casio's user guide states that a connected computer and keyboard can exchange MIDI and that MIDI can be sent from the computer to the keyboard for playback. This is the critical requirement that eliminated devices whose USB MIDI receive behavior was undocumented.

## Documented capabilities relevant to the project

- AiX sound source
- 600 built-in tones
- maximum polyphony: 48 voices; some tones may impose lower effective limits
- USB Type-B MIDI port
- class-compliant USB-MIDI
- General MIDI Level 1 compatibility
- MIDI receive into the internal sound generator
- Note On / Note Off
- velocity
- Program Change
- Bank Select
- control changes including sustain
- multi-part receive suitable for multichannel arrangements
- percussion/GM arrangement support
- built-in 12 cm × 2 speakers
- 2.5 W + 2.5 W amplification
- PHONES/OUTPUT stereo jack
- pedal input
- 9.5 V DC adapter class (AD-E95100L listed by Casio)

## Manufacturer evidence

- Product/specifications: https://www.casio.com/us/electronic-musical-instruments/product.CT-X700/
- Support page: https://www.casio.com/intl/electronic-musical-instruments/support.CT-X700/
- User guide: https://www.casio.com/content/dam/casio/global/support/manuals/electronic-musical-instruments/pdf/008-en/w/Web_CTX700-ES-1A_EN.pdf
- MIDI implementation: https://www.casio.com/content/dam/casio/global/support/manuals/electronic-musical-instruments/pdf/008-en/c/CT-X700-midi-imple_EN.pdf

## Why 61 physical keys are not a blocker

OpenOrchestrion is not purchasing the CT-X700 for human keyboard performance. The physical keybed does not define what the internal MIDI sound generator can receive. The project therefore treats physical key count, weighted action, and key feel as low-priority characteristics.

The primary value is the sound engine, MIDI receive behavior, predictable GM-style mapping, polyphony, built-in audio, documentation, and cost.

## Multi-instrument use

The CT-X700 can render more than piano. A multi-channel MIDI arrangement can request separate parts such as:

```text
Channel 1   Grand Piano
Channel 2   Acoustic Bass
Channel 3   Strings
Channel 4   Trumpet
Channel 5   Saxophone
Channel 10  Drums
```

This capability was the architectural step that expanded the project from a modern player piano into OpenOrchestrion: a networked MIDI music appliance.

## Polyphony caution

Forty-eight voices are useful but finite. Sustained piano passages and dense ensemble arrangements may cause voice stealing. The OpenOrchestrion MIDI analyzer should estimate polyphony demand, and a second hardware sound engine may distribute demanding arrangements across independent synthesis engines.

## Required project validation

A physical unit should not be promoted from `documented` to `project-validated` until it passes:

1. Linux/Pi enumerates the MIDI endpoint.
2. Host-sent Note On/Off produces internal audio.
3. Velocity differences are verified.
4. Sustain CC64 is verified.
5. Program Change is verified.
6. Bank Select behavior is characterized.
7. A multichannel GM file renders multiple instruments.
8. Channel 10 percussion is verified.
9. An expressive solo-piano performance is played end-to-end.
10. Dense sustained material is used for polyphony stress testing.
11. Long-duration playback is stable.
12. USB disconnect/reconnect and power-cycle behavior are documented.
13. USB endpoint identity is recorded for reliable device matching.
14. Actual MIDI-to-audio latency is measured for future multi-device compensation.

The hardware-proof GitHub issue is the authoritative place to record test results.

## Audio upgrade path

The built-in speakers are sufficient for the initial appliance proof. The PHONES/OUTPUT connection gives the project a straightforward future path to external powered speakers or another amplification system without changing the MIDI architecture.

## Status

**Documented compatible / reference candidate. Physical OpenOrchestrion validation pending.**
