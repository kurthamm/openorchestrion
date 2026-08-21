# Hardware Selection

## Selection principle

OpenOrchestrion is not buying a keyboard for a human performer. It is buying a **MIDI-addressable hardware sound engine with speakers that happens to have keys attached**.

Therefore the normal digital-piano buying hierarchy changes.

## Mandatory requirements for a recommended device

- Documented or physically verified **MIDI receive** from host to internal sound engine.
- Incoming Note On / Note Off support.
- Velocity support.
- Sustain (CC64) support.
- Reliable Linux-compatible MIDI transport, preferably class-compliant USB MIDI.
- Internal sound generation and usable audio output.

## Strongly preferred

- General MIDI or similarly predictable program mapping.
- Multitimbral receive.
- Program Change and Bank Select.
- 48 or more voices of polyphony.
- Built-in speakers.
- Line/headphone output for future external amplification.
- Manufacturer-published MIDI implementation documentation.
- Stable model identification over USB.

## Low-priority characteristics for this project

- Weighted action.
- Key feel.
- Hammer simulation.
- Number of physical keys.
- Lesson modes.
- Built-in songs.
- Human-facing arranger UI.

A 61-key model can be preferable to an 88-key model if its internal MIDI engine receives the required note range and has better synthesis, polyphony, connectivity, documentation, or price.

## Polyphony

Expressive piano MIDI with sustain can consume voices quickly. Full arrangements can consume more. Forty-eight voices is a practical baseline target for inexpensive devices; more is better.

Two devices do not create a mathematically guaranteed doubled polyphony number, but split routing can substantially reduce voice stealing by distributing parts across independent synthesis engines.

## Second-device strategy

A second keyboard is most valuable when it provides a complementary sound engine rather than merely duplicating the first. The current conceptual pairing is:

- Casio CT-X700: AiX engine, GM/multitimbral role.
- Yamaha PSR-EW310/EW300/E363: complementary Yamaha AWM sound set.

A routing profile can choose the preferred engine by instrument family.

## Procurement rule

For used/auction hardware, evaluate **delivered cost**, not bid price alone:

`delivered_cost = bid + shipping + handling + tax + required power supply/adapters`

Because auction devices carry greater risk than tested retail used gear, the target price should retain a meaningful discount relative to known-good used-market pricing.
