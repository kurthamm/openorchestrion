# Two-Piano and Dueling-Piano Mode

## Why this matters

A second MIDI sound engine lets OpenOrchestrion do something qualitatively different from merely increasing polyphony: reproduce music written for two independent pianos and create arrangements that intentionally trade phrases between two devices.

```text
                    Master timeline
                         │
              ┌──────────┴──────────┐
              │                     │
          Piano I               Piano II
              │                     │
           Device A              Device B
```

## Performance categories

### `TWO_PIANO`

Music written for two independent pianos. This is the cleanest use case because Piano I and Piano II already have distinct musical identities.

### `PIANO_DUET`

Four-hands or duet music originally intended for two performers at one piano. It can be rendered on two devices when the MIDI file preserves separable Primo/Secondo parts or can be safely transformed into that structure.

### `DUELING_PIANO`

An OpenOrchestrion arrangement designed around call-and-response, alternating verses, accompaniment/solo exchanges, or a combined finale. This is not limited to historical “dueling piano” repertoire; it is a routing/arrangement model.

Example structure:

```text
Device A      intro ────────────────┐
                                    │
Device B              answer ──────┤
                                    │
Both                       chorus ──┤
Device A      solo ─────────────────┤
Device B              solo ─────────┤
Both                       finale ──┘
```

## Proof-of-concept repertoire

### Mozart: Sonata for Two Pianos in D major, K.448

This is an ideal early demonstration because it is genuine two-piano repertoire rather than an artificial split. OpenOrchestrion should locate/use a MIDI source with redistribution terms compatible with the intended use and preserve the Piano I/Piano II structure.

### Diabelli: 28 melodische Übungsstücke, Op. 149

Mutopia publishes piano-duet MIDI for this collection under Creative Commons Attribution-ShareAlike 3.0. It is useful for validating separable duet material and rights-aware library ingestion.

Source examples:

- https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=389
- https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=564

### Wikimedia Commons

Wikimedia Commons maintains a category for compositions for two pianos, including MIDI media whose individual file licenses must be checked before redistribution:

- https://commons.wikimedia.org/wiki/Category:Compositions_for_two_pianos

## Library metadata

Two-device material should support fields such as:

```json
{
  "performance_type": "TWO_PIANO",
  "parts": [
    {"role": "piano_1", "track": 1, "preferred_device_role": "piano_a"},
    {"role": "piano_2", "track": 2, "preferred_device_role": "piano_b"}
  ]
}
```

For dueling arrangements, metadata may additionally describe sections or routing changes over time.

## Routing requirements

- Parts must be routable independently.
- Both devices must follow one master sequencer/timeline.
- A per-device latency offset must be supported.
- Stop/Panic must reach both devices.
- If one device disappears, the performance profile must define whether to stop, continue one part, or attempt fallback routing.

## Synchronization

Two adjacent keyboards connected to the same Pi should not run independent playback engines. One scheduler emits all events against a common timeline and routes them to separate MIDI ports.

Device processing latency may differ by a few milliseconds. OpenOrchestrion should measure and compensate that difference where needed. Identical notes played on both engines are the most sensitive calibration test because small offsets can produce audible doubling/chorusing.

Physical speaker distance also matters. Acoustic propagation through the room can exceed the electronic timing difference when devices are widely separated.

## Dueling-piano library policy

Purpose-built OpenOrchestrion arrangements of public-domain/openly licensed compositions can be redistributed when the underlying rights allow it.

Arrangements of modern copyrighted popular music may still be useful in a user's Personal Library, but the public repository must not assume that an arrangement is redistributable merely because a MIDI file is available online.

## Future arranger tools

A future AI-assisted or rule-based arranger may help transform material into two-device form, for example:

- separate left/right or Primo/Secondo material;
- assign melody and accompaniment to different engines;
- alternate repeated sections;
- produce call-and-response routing;
- generate a combined finale;
- choose different tone palettes for each device.

This is an advanced feature. Stable deterministic playback and routing come first.

## Demo milestone

A compelling public demonstration is:

1. two physical keyboards beside one another;
2. one Raspberry Pi master timeline;
3. a true two-piano MIDI work;
4. Piano I clearly routed to one device and Piano II to the other;
5. synchronized audible playback;
6. the touchscreen showing both active parts/devices.
