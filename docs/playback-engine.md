# Playback Engine

## Goal

OpenOrchestrion owns playback on the server. A browser can disconnect, sleep, or
be replaced and the music timeline keeps running. The web application renders
state and sends commands; it never owns the queue or MIDI clock.

The first playback implementation is hardware-neutral and can run entirely
against in-memory virtual MIDI outputs. Real `mido` output ports sit behind the
same interface.

## Core pipeline

```text
QueueItemSpec
     │
     ▼
MIDI timeline parser
     │
     ▼
one master monotonic clock
     │
     ▼
RoutingPlan / latency offsets
     │
     ├──────────────┐
     ▼              ▼
 MIDI output A   MIDI output B
     │              │
     ▼              ▼
 sound engine A  sound engine B
```

A two-keyboard performance is not two independent players. Both destinations
receive events scheduled from the same timeline.

## Server-owned state

The playback engine owns:

- the authoritative ordered queue;
- current queue index;
- transport state;
- current timeline position;
- the active scheduling task;
- durable play-history lifecycle;
- MIDI output cleanup;
- command-id idempotency;
- state-change events consumed by the WebSocket layer.

Public transport states match the API contract:

```text
idle
playing
paused
stopped
```

Errors are emitted separately as typed error events rather than being hidden in
browser-local state.

## Queue behavior

The API can fill the queue from either:

1. a validated `PlaybackIntent`, which is resolved by Smart Stations; or
2. an explicit list of catalog asset IDs.

A request must choose exactly one source. Queue replacement interrupts active
playback safely. Append preserves the current queue and adds new material.

The engine rejects duplicate asset IDs in one queue because queue mutations in
the current API identify entries by `asset_id`.

## Transport

### Play

Starts the current queue item. Calling play while paused resumes from the saved
musical position.

### Pause

Pause captures the current monotonic position, cancels the active scheduler, and
sends cleanup MIDI so notes cannot hang. Resume reconstructs stateful channel
messages that occurred before the resume point, such as Program Change,
controllers, pitch wheel, and channel aftertouch.

The first implementation intentionally does **not** reconstruct notes that were
held across a pause point. Resume therefore starts cleanly from subsequent MIDI
note events rather than attempting to synthesize the exact acoustic sustain that
would have existed without interruption.

### Stop

Stops the active item, records the interrupted history attempt as skipped, sends
cleanup to every output, and leaves the queue loaded at the current item.

### Skip

Terminates the current attempt as skipped and advances to the next queue item.
If playback was active, the next item starts automatically.

### Panic

Cancels active playback and fans cleanup across every configured MIDI output and
all 16 channels:

- CC64 = 0, sustain off;
- CC120 = 0, All Sound Off;
- CC123 = 0, All Notes Off.

Cleanup continues to other outputs even if one destination raises an error.

## Automatic advance

At normal completion the engine:

1. records the play as completed;
2. sends cleanup;
3. advances the canonical queue index;
4. starts the next item from the same server-owned playback service;
5. emits queue/playback state changes.

No browser connection is required for this sequence.

## Timing model

Playback timing uses a monotonic clock. `SystemClock` is used by the appliance;
`ManualClock` is a deterministic test clock so scheduler tests advance logical
time instead of sleeping in real time.

Mido's merged `MidiFile` iterator supplies tempo-aware event delays. The playback
layer converts those into absolute musical seconds and schedules every output
from that one timeline.

Device latency is represented as a positive per-route delay. If one engine is
measured 3 ms faster than another, the faster route can be delayed by 3 ms.

## Routing

`MidiRoute` and `RoutingPlan` are reused rather than embedding device checks in
the scheduler. Internally they use Mido's zero-based channel convention:

```text
0..15 internally == MIDI channels 1..16 in user-facing terminology
```

Example two-piano plan:

```python
RoutingPlan([
    MidiRoute(source_channel=0, destination_device="piano-a"),
    MidiRoute(source_channel=1, destination_device="piano-b"),
])
```

The generated `two-piano-split.mid` fixture is the reference acceptance test for
this behavior.

## SysEx policy

Arbitrary SysEx is **not sent by default**. The importer/analyzer may inspect and
report SysEx, but playback suppresses it unless an explicitly trusted future
configuration enables it. This preserves the architecture rule that imported
MIDI data is not an unrestricted device-command channel.

## Virtual MIDI mode

For development without a keyboard:

```bash
export OPENORCHESTRION_VIRTUAL_MIDI=1
```

The application exposes an in-memory output named:

```text
OpenOrchestrion Virtual
```

The same state machine, queue API, history flow, routing, and WebSocket state are
used. Only the final output implementation changes when physical hardware is
present.

## Durable history

Queueing creates a durable play attempt. Starting, substantial listening,
completion, skips, and failures flow through the existing history module.

A completed item always counts as played. A partial play counts for no-repeat
purposes only after the history module's substantial-listen threshold. A quick
skip therefore does not poison the no-repeat window.

Station/Concierge previews and queue generation merge the configured recent-play
window back into `StationConstraints`, closing the loop between playback and
future selection.

On orderly application shutdown, active playback is stopped before ports are
closed so the durable history row cannot remain indefinitely in a started state.

## WebSocket state

The playback event bus assigns monotonically increasing sequence numbers to
state changes. A client receives a complete snapshot at connection time and can
request another with:

```json
{"type": "state.request_snapshot"}
```

If a slow subscriber overflows its local event queue, old deltas are dropped.
That intentionally creates a sequence gap, causing the client to discard its
partial local view and request a fresh snapshot rather than attempt unreliable
reconciliation.

The position anchor sent to clients uses server time for diagnostics only. The
browser anchors interpolation at local message receipt time, as defined in the
API contract.

## Failure behavior

Before playback begins, the current MIDI file is parsed and the routing plan is
resolved. A missing asset or unavailable destination fails the attempt rather
than beginning a half-valid timeline.

A runtime MIDI-output failure:

- terminates the durable history attempt as failed;
- cancels the active timeline;
- attempts panic cleanup on every output;
- emits an error event and a stopped playback state.

## Test strategy

Hardware-free tests cover:

- generated single-note playback through a virtual output;
- pause/resume position preservation;
- skip/history behavior;
- automatic queue advance;
- stop/panic cleanup fan-out;
- command-id idempotency;
- missing-file failure;
- two-piano routing to two virtual destinations from one master timeline.

Physical CTK-6200 and PSR-EW300 validation later replaces the virtual destination
with real ports without changing the playback ownership model.
