# Architecture Decision Records

OpenOrchestrion records consequential design decisions as ADRs so future contributors can understand **why** the architecture has particular boundaries rather than only seeing the resulting code.

Status values:

- `Accepted`
- `Proposed`
- `Superseded`
- `Deprecated`

Current ADRs:

1. [ADR-0001: Local-first playback](0001-local-first-playback.md)
2. [ADR-0002: Treat attached keyboards as hardware sound engines](0002-keyboard-as-sound-engine.md)
3. [ADR-0003: AI interprets intent but never directly drives MIDI](0003-ai-intent-boundary.md)
4. [ADR-0004: One master timeline for locally connected MIDI devices](0004-single-master-timeline.md)
5. [ADR-0005: One responsive web application for kiosk and remote control](0005-single-web-ui.md)
6. [ADR-0006: Durable library metadata must survive SQLite rebuild](0006-durable-library-metadata.md)
7. [ADR-0007: Recommended hardware requires documented or verified MIDI receive](0007-midi-receive-evidence.md)
