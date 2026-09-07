# Two-Engine MIDI Orchestra: recommendation and requirements

Status: **planned**. This is the agreed target for the reference build once the
second keyboard (Casio CT-X700) joins the Casio WK-220. It extends the existing
[routing engine](routing-engine.md) and [multi-device playback](multi-device.md)
rather than replacing them: track/channel routing, device profiles, polyphony
load estimation, latency offsets and one shared scheduler already exist. What is
new here is the orchestration policy on top of them — engine roles, instrument
affinity as configuration, planning limits, song-specific plans, single-engine
fallback and a visible plan in the UI. Tracking issue: see the GitHub issue
"Two-engine MIDI orchestration (CT-X700 + WK-220)".

Already in place (September 2026): device profiles under `device-profiles/`
(`DeviceProfile` in `models.py`), `plan_routing()` with instrument-family
affinity, per-device load balancing and latency delays, `MidiOutputRouter` with
per-destination routing of every channel message, hot-plug detection with pause
and resume, `reset_channels()` and panic fan-out to every output, automatic
voicing for score exports, and the rendering-before-routing order.

Gaps this document closes: engine role priorities and affinity scores as
configuration data; a polyphony planning limit below nominal; whole-song load
balancing that may override affinity; song-specific orchestration profiles in
the sidecar; manual per-part overrides in the UI; the orchestration plan shown
to the listener and logged with reasons; explicit re-orchestration when an
engine is missing.

---

## 1. Recommendation

The player-piano project should support multiple physical MIDI sound engines as a coordinated orchestral system rather than treating additional keyboards as backups or duplicate playback devices.

The initial deployment should use:

* **Casio CT-X700** as the higher-quality foreground sound engine.
* **Casio WK-220** as the supporting sound engine for accompaniment, rhythm, bass, pads, and other less exposed parts.
* **Raspberry Pi** as the conductor responsible for analyzing MIDI files and dynamically assigning MIDI parts to the most appropriate sound engine.

The goal is to create a **two-instrument MIDI orchestra** in which each keyboard performs the parts best suited to its sound engine while the software also distributes polyphony and playback load across both devices.

This architecture should be designed generically so that additional keyboards, synthesizers, rack modules, software synthesizers, or other MIDI destinations can be added later without redesigning the playback engine.

## 2. Design principle

The system must not assume:

> MIDI Channel 1 always goes to Keyboard A.

Instead, playback routing should be based on:

1. Instrument type
2. Sound-engine preference
3. Available polyphony
4. Current voice load
5. Sustain behavior
6. MIDI channel requirements
7. Drum/percussion requirements
8. Device capabilities
9. User-configured preferences
10. Song-specific overrides

The Raspberry Pi should act as the **orchestrator** rather than merely as a MIDI file player.

```text
                        MIDI File
                            |
                            v
                    MIDI Analysis Layer
                            |
                            v
                  Orchestration / Routing
                       /            \
                      /              \
                     v                v
               Casio CT-X700      Casio WK-220
               Foreground Engine  Support Engine
```

## 3. Initial engine roles

### 3.1 Casio CT-X700

The CT-X700 should normally receive musical parts where timbre and articulation are most noticeable: acoustic piano, electric piano, acoustic and electric guitar, solo and lead strings, brass and solo brass, woodwinds, saxophone, lead instruments, and other exposed melodic parts.

The CT-X700 should generally be considered the **preferred foreground engine**. This does not mean every song must use it for these instruments. Routing must remain dynamic.

### 3.2 Casio WK-220

The WK-220 should normally handle supporting parts where its older sound engine is less consequential: bass, drum kit, percussion, organ, string ensemble, pads, background accompaniment, secondary harmony, sustained textures, simple electric-piano accompaniment, and other rhythm-section or supporting parts.

The WK-220 should generally be considered the **support engine** and a source of additional polyphony.

## 4. Important exception: solo piano

For a solo-piano MIDI file, the default should be:

```text
Entire performance -> CT-X700
```

Do not arbitrarily divide a solo piano performance between the two keyboards. Splitting one piano performance across two different sound engines could create audible inconsistencies in tone, velocity response, sustain, attack, decay, reverb, and stereo image. A split-piano mode may be experimented with later, but it should not be the default.

## 5. Core requirement: engine profiles

The software must introduce a generic **MIDI Engine Profile** abstraction. Each connected MIDI sound device should have a profile describing its capabilities and preferences. (The existing `device-profiles/*.json` and `DeviceProfile` model are the starting point; the `role` and `instrument_affinity` blocks below are the additions.)

```yaml
engine:
  id: casio_ctx700
  name: Casio CT-X700
  transport:
    type: usb_midi
  capabilities:
    midi_channels: 16
    max_polyphony: 48
    drums: true
    program_change: true
    bank_select: true
    control_change: true
    sustain: true
  role:
    foreground_priority: 90
    accompaniment_priority: 60
  instrument_affinity:
    piano: 100
    electric_piano: 95
    guitar: 90
    strings_solo: 90
    brass: 85
    woodwind: 85
    bass: 60
    organ: 60
    pads: 55
    drums: 60
```

```yaml
engine:
  id: casio_wk220
  name: Casio WK-220
  transport:
    type: usb_midi
  capabilities:
    midi_channels: 16
    max_polyphony: 48
    drums: true
    program_change: true
    bank_select: true
    control_change: true
    sustain: true
  role:
    foreground_priority: 55
    accompaniment_priority: 90
  instrument_affinity:
    piano: 65
    electric_piano: 65
    guitar: 60
    strings_solo: 60
    strings_ensemble: 85
    brass: 60
    woodwind: 60
    bass: 90
    organ: 85
    pads: 90
    drums: 95
```

These values should be configuration data, not hard-coded application logic.

## 6. Core requirement: instrument affinity

The orchestration engine must support an **Instrument Affinity Score**: how desirable a particular sound engine is for a particular MIDI instrument or instrument family.

```text
0   = unsuitable
25  = poor
50  = acceptable
75  = preferred
100 = strongly preferred
```

```text
Instrument Family       CT-X700    WK-220
------------------------------------------
Piano                    100         65
Electric Piano            95         65
Acoustic Guitar           90         60
Electric Guitar           90         60
Bass                      60         90
Solo Strings              90         60
String Ensemble           75         85
Brass                     85         60
Woodwinds                 85         60
Organ                     60         85
Pads                      55         90
Drums                     60         95
Percussion                60         95
```

The orchestration engine should use these values as one input into routing decisions. They are preferences, not absolute rules.

## 7. MIDI file analysis requirements

Before playback, the application should analyze the MIDI file and build a track/part model. For each track or logical part, determine where possible: MIDI channel; program number; bank selection; General MIDI instrument; instrument family; whether channel 10 is used for percussion; note range; note count; maximum simultaneous sounding notes; sustain, pitch-bend, modulation and expression usage; channel volume; pan; track duration; average and maximum velocity; density; and whether the track appears melodic or accompaniment-oriented. (The deterministic analyzer already records most of these in the sidecar; role estimation is the addition.)

```text
Part 1   Channel 1    Acoustic Grand Piano   Family: Piano       Peak voices: 22   Role: Foreground
Part 2   Channel 2    Fingered Bass          Family: Bass        Peak voices: 4    Role: Support
Part 3   Channel 10   Standard Drum Kit      Family: Percussion  Peak voices: 9    Role: Rhythm
Part 4   Channel 4    String Ensemble        Family: Strings     Peak voices: 18   Role: Background
Part 5   Channel 5    Trumpet                Family: Brass       Peak voices: 3    Role: Foreground
```

## 8. Routing decision requirements

The routing engine should calculate a score for every valid `MIDI Part -> MIDI Engine` combination, considering at least instrument affinity, foreground/support preference, available polyphony, predicted peak load, device capability, user preference, song-specific override, an overload penalty and an unsupported-feature penalty.

```text
score =
    instrument_affinity
  + role_affinity
  + available_capacity_bonus
  + user_preference
  - polyphony_risk
  - capability_penalty
```

The exact scoring algorithm can evolve. The architecture is more important than the initial formula.

## 9. Polyphony-aware routing

Each keyboard has a finite voice budget. The project treats each sounding `(channel, note)` combination as one occupied voice and avoids counting repeated notes under sustain as multiple independent voices. The multi-engine orchestrator should extend that model: for every candidate assignment, estimate the maximum simultaneous sounding voices assigned to each engine.

```text
CT-X700: Piano 22 + Trumpet 3 + Lead Strings 8  = estimated peak 33
WK-220:  Bass 4 + Drums 9 + String Pad 15       = estimated peak 28
```

This assignment is desirable because both devices remain comfortably below their nominal 48-voice limits.

## 10. Polyphony safety margin

Do not plan routing all the way to exactly 48 voices. Internal synthesis may consume polyphony differently depending on stereo samples, layered tones, sustain, percussion, effects and the sound-engine implementation. Introduce a configurable safety threshold:

```yaml
polyphony:
  nominal: 48
  planning_limit: 40
```

Suggested initial planning limit: 80–85% of nominal, i.e. roughly 38–41 voices for a 48-voice device. Configurable per engine.

## 11. Dynamic load balancing

Routing should optimize across the entire song rather than independently assigning each track.

```text
Bad:     CT-X700  Piano 30 + Strings 20 + Trumpet 4 = 54     WK-220  Bass 4 + Drums 8 = 12
Better:  CT-X700  Piano 30 + Trumpet 4 = 34                   WK-220  Strings 20 + Bass 4 + Drums 8 = 32
```

The second arrangement sacrifices some string-engine affinity but produces a much safer overall orchestration. Polyphony balancing must be able to override a simple affinity preference.

## 12. Routing granularity

Version 1 routes at the level of MIDI track / MIDI channel. Do not initially route individual notes from a single channel to different keyboards. Note-range splits, velocity splits, piano hand splitting, ensemble duplication and orchestral layering are explicitly out of scope for the first implementation.

## 13. MIDI message routing

Once a part has been assigned to a destination engine, all related channel messages must be routed consistently to that engine: Note On/Off, Program Change, Bank Select, Sustain, Modulation, Expression, Channel Volume, Pan, Pitch Bend, Aftertouch where applicable, and other supported Control Change messages. Never route notes to one device and their controllers to another. (`MidiOutputRouter` already guarantees this per route.)

## 14. Global MIDI messages

Explicitly handle All Notes Off, Reset All Controllers, System Reset, GM Reset and Master Volume. Global reset or panic commands go to every active sound engine. A stop, abort, error or song change must never leave sustained or hanging notes on either keyboard. (Panic, `reset_channels()` and the master-volume fan-out already cover every output.)

## 15. Drum routing

Default: `Drums / percussion -> WK-220`, unless the CT-X700 kit is explicitly preferred, the WK-220 is approaching its polyphony limit, the user overrides the assignment, or listening tests show certain kits sound materially better on the CT-X700. Drums are a high-value offload because they consume substantial instantaneous polyphony.

## 16. Foreground vs background classification

The analyzer should eventually classify tracks into roles: Foreground, Background, Rhythm, Bass, Harmony, Pad, Lead, Unknown. Initial classification may rely on heuristics — melody instruments, solo brass/strings, saxophone, prominent piano and guitar lead are likely foreground; bass, drums, sustained pads, string ensemble, rhythm guitar and accompaniment organ are likely support. Role classification influences, but does not dictate, routing.

## 17. User interface requirements

The player UI should expose the orchestration decision without requiring MIDI knowledge:

```text
MIDI Orchestra

CT-X700
  Acoustic Grand Piano
  Trumpet
  Nylon Guitar

WK-220
  Fingered Bass
  Standard Drum Kit
  String Ensemble

Estimated peak:
  CT-X700: 31 / 48
  WK-220: 27 / 48
```

## 18. Manual overrides

For each MIDI part the user can choose `Auto`, `CT-X700` or `WK-220`. Manual assignments persist for the current song and can optionally be saved as song metadata.

## 19. Song-specific orchestration profile

Routing decisions can be stored alongside the MIDI library (in the asset sidecar's curated block, so they survive catalog rebuilds):

```yaml
orchestration:
  mode: automatic
  assignments:
    channel_1:  { engine: casio_ctx700 }
    channel_2:  { engine: casio_wk220 }
    channel_10: { engine: casio_wk220 }
```

A song is analyzed once, tuned manually if desired, and played consistently thereafter.

## 20. Engine discovery

Detect available MIDI output devices at startup and map physical endpoint names to configured engine profiles. If one keyboard is disconnected, fall back gracefully to single-engine playback and say so: "WK-220 unavailable. Re-orchestrating song for CT-X700 only." Never simply discard tracks assigned to the missing device. (Hot-plug detection exists; re-orchestration is the addition.)

## 21. Single-engine fallback

Any song playable in orchestra mode must remain playable with one engine. Modes: `AUTO_MULTI_ENGINE`, `AUTO_SINGLE_ENGINE`, `MANUAL`. With one device, all compatible channels go to it, with warnings if predicted polyphony exceeds its configured limit.

## 22. Future multi-engine scalability

The routing layer operates on a list of engines, never on `primary_keyboard` / `secondary_keyboard`. Future engines may include other keyboards, sound modules, USB synthesizers, FluidSynth or a Pi software synth, or an external drum module. Adding a third engine must not require a routing redesign.

## 23. Suggested domain model

```text
MidiSong
 ├── MidiPart[]        channel, program, instrument_family, role, peak_polyphony, midi_features
 └── OrchestrationPlan
      └── PartAssignment[]   part_id, engine_id, score, estimated_peak, assignment_reason, manual_override

MidiEngine
 ├── EngineProfile
 ├── MidiEndpoint
 ├── PolyphonyCapacity
 ├── InstrumentAffinity
 └── Capabilities
```

`assignment_reason` matters for diagnostics and UI transparency, e.g. "Trumpet -> CT-X700: affinity +85, foreground +20, capacity +10, final 115".

## 24. Logging requirements

Log the final orchestration plan per song: each engine's parts, predicted peak voices and planning limit. When the optimizer chooses a lower-affinity engine because of capacity, log that decision and its reason.

## 25. Playback synchronization

Both outputs are driven from one playback clock: shared timeline, shared scheduler, independent destinations, deterministic ordering, minimal inter-device skew, and never separate players per keyboard. (This is how the engine already works; see [playback engine](playback-engine.md).)

## 26. Startup initialization

Before playback, initialize each keyboard: reset / all notes off, bank/program, volume, pan, controller defaults, reverb/chorus where appropriate. The sequence is engine-configurable because different keyboards may need different startup messages.

## 27. Effects strategy

Do not model effects as "CT-X700 = chorus, WK-220 = reverb". Effects stay inside each engine; the profile may later carry effect-quality ratings that influence scoring. Not required for the first implementation.

## 28. Initial routing defaults

```text
CT-X700: piano, electric piano, acoustic guitar, electric guitar, solo strings, brass, woodwinds, lead synth
WK-220:  bass, drums, percussion, organ, string ensemble, pads, background synth, rhythm accompaniment
```

To be tuned after actual listening tests.

## 29. Acceptance criteria

- **AC1 Device detection**: both keyboards detected independently as destinations.
- **AC2 Engine profiles**: each keyboard represented by a configurable profile.
- **AC3 Song analysis**: each part identified with its GM instrument family.
- **AC4 Automatic routing**: parts assigned to CT-X700 or WK-220 automatically.
- **AC5 Affinity routing**: foreground parts prefer the CT-X700; bass, drums, pads and similar prefer the WK-220.
- **AC6 Polyphony balancing**: overload avoided when an alternative distribution exists.
- **AC7 Correct controllers**: program changes, sustain, volume, pan, pitch bend and other channel messages follow their notes.
- **AC8 Shared timing**: one scheduler keeps both keyboards synchronized.
- **AC9 Manual override**: a part can be forced to either keyboard.
- **AC10 Single-keyboard fallback**: playback continues with one keyboard.
- **AC11 Panic / stop**: releases notes on both devices.
- **AC12 Visible plan**: the UI shows which instruments went to which keyboard.

## 30. Phase recommendation

1. **Phase 1**: architecture and deterministic routing (CT-X700: piano, guitar, brass, woodwinds, solo strings; WK-220: bass, drums, organ, pads, string ensemble), polyphony checks, manual overrides.
2. **Phase 2**: scoring-based orchestration using affinity, role, predicted polyphony and engine load.
3. **Phase 3**: listening-derived sound profiles — actual preference ratings from side-by-side tests, eventually per GM program rather than per family.
4. **Phase 4**: additional engines orchestrated by the same optimizer.

## 31. Long-term vision

```text
MIDI File -> Analyze Composition -> Identify Instruments -> Estimate Polyphony
          -> Select Best Sound Engine -> Balance Orchestration -> Route MIDI
                                              +--> CT-X700
                                              +--> WK-220
                                              +--> Future Engine
```

**Multi-engine MIDI orchestration** becomes a defining capability: the Raspberry Pi is not merely pressing Play. It conducts a small collection of hardware synthesizers, deciding which instrument performs each part based on musical role, sound quality and available capacity. The CT-X700 and WK-220 are the first two musicians in that orchestra.
