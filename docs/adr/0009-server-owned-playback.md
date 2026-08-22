# ADR-0009: Server-owned playback state and timeline

- **Status:** Accepted
- **Date:** 2026-08-22

## Context

OpenOrchestrion has multiple control surfaces: the attached kiosk and household browsers. A browser can sleep, disconnect, reconnect, or disappear while music should continue. Multi-device MIDI also requires one authoritative musical clock rather than independent client-side players.

## Decision

The FastAPI application owns one long-lived playback service. That service owns the queue, current item, transport state, monotonic position, scheduling task, MIDI routing, cleanup, and durable history lifecycle.

Browsers send commands over REST and receive authoritative snapshots/deltas over WebSocket. They may interpolate progress locally for display and may show reversible optimistic UI, but they do not own or advance playback state.

The scheduler uses one master monotonic timeline for all locally connected outputs. `RoutingPlan` selects destinations and route latency offsets compensate measured device differences.

A virtual MIDI output implements the same destination interface as physical Mido ports so playback can be developed and tested before hardware arrives.

## Consequences

- Music continues when every browser disconnects.
- Multiple clients converge on the same queue and transport state.
- Two-keyboard playback is synchronized from one scheduler.
- WebSocket reconnects can replace client state wholesale from a server snapshot.
- Durable history is emitted by actual server playback rather than UI button presses.
- The web application cannot accidentally become a second timing engine.
- A server restart interrupts playback and is recorded as such before MIDI outputs close.
