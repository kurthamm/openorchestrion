# ADR-0003: AI interprets intent but never directly drives MIDI

- **Status:** Accepted
- **Decision:** AI providers may produce a structured `PlaybackIntent` and descriptive metadata suggestions. They do not receive direct access to MIDI outputs or arbitrary device commands.

## Context

Natural language is ideal for requests such as “play dinner music” or “popular Christmas music,” but an LLM is probabilistic and may invent fields, devices, commands, or unsupported behavior.

## Consequences

- AI output is schema-validated.
- The deterministic selector chooses actual library items.
- The deterministic router/sequencer owns hardware execution.
- AI provider failure leaves manual/station playback functional.
- AI cannot fabricate a SysEx command and send it directly to hardware.
- Local, hosted, or OpenAI-compatible providers can share one contract.
