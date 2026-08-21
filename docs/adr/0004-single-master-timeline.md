# ADR-0004: One master timeline for locally connected MIDI devices

- **Status:** Accepted
- **Decision:** Multiple sound engines attached to one host are scheduled from one canonical playback timeline. Each device is an output destination, not an independent player.

## Context

Independent players create avoidable synchronization and drift problems. One Pi can schedule all track/channel events from the same song clock and route them to separate ports.

## Consequences

- Pause/resume/seek affects the whole performance coherently.
- Two-piano parts remain aligned.
- Per-device MIDI-to-audio latency can be compensated with offsets.
- Stop/Panic can fan out to every active destination.
- Distributed multi-room endpoints are a separate future architecture using pre-staged files and coordinated start timestamps.
