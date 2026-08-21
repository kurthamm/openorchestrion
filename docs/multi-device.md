# Multi-Device Playback

## Why multiple sound engines

A second keyboard can provide more than redundancy:

- distribute polyphony load;
- use different manufacturers for different instrument families;
- reproduce true two-piano music;
- build purpose-designed dueling-piano arrangements;
- create spatial/antiphonal playback;
- support future multi-room endpoints.

## Same-Pi synchronization

For two keyboards beside each other, one Pi is the preferred architecture.

```text
                  Raspberry Pi
                 MASTER TIMELINE
                      │
                MIDI scheduler
                 ┌────┴────┐
                 │         │
              USB A      USB B
                 │         │
                 ▼         ▼
             Device A   Device B
```

Both outputs are scheduled from the same musical clock. The devices are not independently playing copies of the file.

## Device latency

Each sound engine introduces a small MIDI-to-audio delay. Device profiles therefore include a configurable latency offset.

Example:

```text
Measured latency:
Casio  = 4.2 ms
Yamaha = 7.1 ms

Compensation:
Casio output delay  = +2.9 ms
Yamaha output delay = 0.0 ms
```

This is especially important when both devices reproduce identical or tightly coupled parts. For different instrument families, a few milliseconds are often musically insignificant, but calibration should still be available.

## Acoustic distance

Physical speaker distance also matters. Sound travels roughly one foot per millisecond. Widely separated speakers can introduce more timing difference at the listener than the USB/MIDI path itself.

## Routing strategies

### Instrument-family routing

```text
Piano      → Yamaha
Strings    → Yamaha
Bass       → Casio
Brass      → Casio
Woodwinds  → Casio
Drums      → Casio
```

### Polyphony-load routing

A complex arrangement can be split across engines to reduce note stealing.

### True two-piano routing

```text
Piano I  → Device A
Piano II → Device B
```

This supports repertoire written for two pianos as well as separated four-hands/duet material.

### Dueling-piano routing

A purpose-built arrangement may trade phrases and solos:

```text
Device A  ── intro ────────────────┐
                                   │
Device B           ── answer ─────┤
                                   │
Both                    ─ chorus ──┤
Device A  ─ solo ──────────────────┤
Device B           ─ solo ─────────┤
Both                    ─ finale ──┘
```

## Failure behavior

If a secondary device disappears during playback, the routing engine should either:

- reroute compatible parts to a remaining engine;
- continue with reduced instrumentation; or
- stop safely and issue all-notes-off.

The chosen behavior should be configurable by performance/routing profile.

## Multi-room future

Do not stream time-critical individual MIDI events over Wi-Fi. Instead:

1. send/cache the complete MIDI asset on each endpoint;
2. synchronize clocks;
3. schedule a future common start timestamp;
4. execute locally on each endpoint.

This makes network jitter a control-plane concern rather than part of the musical clock.
