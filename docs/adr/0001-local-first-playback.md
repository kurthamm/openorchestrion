# ADR-0001: Local-first playback

- **Status:** Accepted
- **Decision:** Time-critical MIDI playback uses local files and local scheduling. Cloud services may support backup, metadata, or AI but are outside the live playback path.

## Context

MIDI files are tiny. Streaming them from Google Drive or another remote store adds network, authentication, provider, and mount failure modes without solving a meaningful storage problem.

## Consequences

- Internet loss does not stop an active queue.
- MIDI timing is not exposed to cloud/network jitter.
- Music is synchronized/downloaded before playback.
- Cloud storage is useful for recovery rather than live rendering.
- Distributed endpoints pre-stage assets and schedule local future starts.
