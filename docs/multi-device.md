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

## Playback rendering policy

Rendering is a reversible playback-time view over an immutable MIDI asset. It
runs after the source has been parsed into the master timeline and before
capability-aware device routing, so a rendered piano part can influence
instrument-family affinity without creating a second sequencer or rewriting the
library.

The precedence rule is:

```text
source arrangement < rendering mode < explicit program override
```

Supported policies are:

- **ORIGINAL**: the default. Preserve the accepted source channels, Bank Select,
  Program Change, percussion and arrangement. With no overrides this is the
  compatibility path and no transformed timeline is needed.
- **PIANO_ONLY**: suppress General MIDI percussion, suppress source Bank Select /
  Program Change that would undo the render, and send pitched parts through a
  selected General MIDI piano program while preserving timing, velocity,
  sustain and track/channel identity.
- **OVERRIDE**: preserve the arrangement while forcing selected pitched MIDI
  channels to specific General MIDI programs.

Rendering preferences live on the queue/playback attempt, not in curated
metadata. The stored `.mid` bytes, SHA-256 identity, deterministic analysis and
sidecars remain unchanged.

The HTTP/application boundary uses MIDI-native numbering consistently with the
playback and routing domains: channels `0..15`, programs `0..127`. General MIDI
percussion channel 10 is therefore internal channel `9` and cannot receive a
pitched override. Program selectors may also use an unambiguous General MIDI
patch name such as `Violin` or `Honky-tonk Piano`; approximate family names and
numeric strings fail closed.

Rendering happens before route planning, but source track/channel identity is
preserved. That is what allows a Piano Only or overridden two-part file to remain
separable across two physical sound engines.

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
