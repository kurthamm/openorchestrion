# ADR-0002: Treat attached keyboards as hardware sound engines

- **Status:** Accepted
- **Decision:** Procurement and software design treat an attached keyboard primarily as a MIDI-addressable hardware sound engine with audio output. Human key action is not a core criterion.

## Context

The target household does not require a person to play the instrument. Traditional digital-piano criteria such as weighted action and physical key count therefore distort the purchasing decision.

## Consequences

Prioritize:

- documented MIDI receive;
- sound quality;
- multitimbral behavior;
- Program Change / Bank Select;
- velocity and sustain;
- polyphony;
- speakers/audio output;
- Linux-compatible transport;
- cost and reliability.

Physical key count matters only when it reflects a limitation of the internal MIDI receive range. A 61-key instrument may be a better OpenOrchestrion device than a more expensive 88-key piano.
