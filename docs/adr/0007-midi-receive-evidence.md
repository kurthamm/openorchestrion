# ADR-0007: Recommended hardware requires documented or verified MIDI receive

- **Status:** Accepted
- **Decision:** A USB connector, MIDI logo, or product-listing claim is insufficient. Recommended OpenOrchestrion hardware must have manufacturer documentation or physical project/community evidence that the host can send MIDI into the internal sound generator.

## Context

The project specifically requires:

```text
host → MIDI → device sound engine → audio
```

Some devices expose USB/MIDI primarily for sending performance data out. Assuming bidirectional behavior creates procurement risk.

## Consequences

Hardware uses three evidence states:

1. `documented`
2. `community-tested`
3. `project-validated`

The original Alesis Recital is not a reference recommendation because inbound behavior is not documented to the project's standard, despite other attractive specifications.

The Casio CT-X700 is a reference candidate because Casio explicitly documents computer-to-keyboard MIDI playback.
