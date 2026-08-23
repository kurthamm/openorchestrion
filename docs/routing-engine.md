# Multi-Device Routing Engine

## Boundary

OpenOrchestrion still has one playback engine and one master timeline. Multi-device
routing decides **where** an event is sent; it never creates a second sequencer or
clock.

The routing planner is deterministic and hardware-neutral. It operates on:

- note-bearing track/channel parts from the MIDI timeline;
- an optional performance type;
- connected output names;
- optional `DeviceProfile` capability data;
- optional device/role preferences.

AI does not route MIDI directly.

## Track and channel identity

Routes can target a channel across the whole file or a specific `(track,
channel)` pair. Track identity matters because two independent piano parts may
both use MIDI channel 1. The playback timeline therefore preserves Standard MIDI
File track numbers instead of flattening that information away.

Multiple equally specific routes may match one source part. That is an explicit
broadcast and is useful for deliberately doubled material.

## Automatic planning

Automatic planning happens when a track starts, not when it is queued. That
means the plan is based on the outputs that actually exist at playback time.
Pause/resume retains the same plan so a part does not jump to another sound
engine halfway through a piece.

The planner uses these priorities:

1. explicit piano roles for `TWO_PIANO`, `PIANO_DUET`, and `DUELING_PIANO`;
2. device/instrument-family affinity from `preferred_instrument_families`;
3. projected keyed-note load divided by nominal device polyphony;
4. stable output-name ordering as the deterministic tie break.

`SOLO_PIANO` remains on one output. OpenOrchestrion does **not** split a normal
solo-piano file merely because the MIDI happens to store left and right hands on
separate tracks.

For paired-piano modes, separable piano parts are assigned alternately to two
distinct outputs. Non-piano accompaniment is balanced after the principal piano
identities are fixed. Current `DUELING_PIANO` routing assumes the arrangement
already encodes independently routable parts; time-section arranging remains a
future arranger responsibility.

## Polyphony load

The routing planner calculates a lightweight, pedal-independent peak of currently
keyed notes per part. This value exists only to distribute work between devices.
It is intentionally separate from the durable analyzer's
`peak_simultaneous_notes` compatibility fact, which includes different semantics
and is corrected/migrated independently.

## Latency compensation

Each endpoint may carry the `latency_offset_ms` from its device profile. The
planner preserves relative offsets but normalizes them so the scheduler never
needs a negative send time. For example:

```text
Configured compensation:
Device A  +2.9 ms
Device B   0.0 ms

Scheduled delay:
Device A  +2.9 ms
Device B   0.0 ms
```

If calibration contains a negative relative value, all endpoints are shifted by
the same amount until the earliest delay is zero. Relative timing is unchanged.

## Device failure

The default failure policy is `stop`.

If an explicitly routed output disappears or throws during playback, the worker
fails the active history attempt, stops playback, and runs Panic across every
remaining configured output. OpenOrchestrion does not silently move Piano II or
a solo part onto another instrument after the performance has begun.

A `drop` policy exists in the low-level routing plan for deliberately disposable
parts, but the automatic planner does not select it.

## Device profiles and physical ports

`VirtualMidiOutput` and `MidoMidiOutput` can carry an optional `DeviceProfile`.
Profiles provide nominal polyphony, instrument-family preferences, and latency
compensation to the planner. Exact physical-port-to-profile binding is deployment
configuration and should be established during reference-hardware validation;
it is not inferred from a USB port name.

## Examples

### True two piano

```text
Track 1 / ch 1  Piano I  -> Device A
Track 2 / ch 1  Piano II -> Device B
```

The shared channel number is not a problem because routes retain track identity.

### Ensemble affinity

```text
Bass part     -> endpoint preferring bass
Strings part  -> endpoint preferring strings
Brass part    -> endpoint preferring brass
Other parts   -> least-loaded compatible endpoint
```

Every event still leaves the same master scheduler.
