# Integrations and Future Extensions

This document captures ideas discussed during the design exploration that are intentionally **not required for the first MVP**. Keeping them visible prevents the core architecture from accidentally blocking useful future directions.

## Home automation

OpenOrchestrion's application API could expose simple commands for Home Assistant or other local automation systems:

- start a station
- stop/pause/resume
- set a requested duration
- request a theme such as Dinner or Christmas
- query Now Playing
- query device health

Examples:

```text
Saturday 5:00 PM
→ start Cocktail / Dinner station
→ play for 90 minutes
```

or eventually:

```text
living room occupied + evening scene
→ resume configured low-volume station
```

Presence-triggered playback should be opt-in and belongs outside the core musical timing engine.

## Voice control

Speech-to-text can feed the existing AI Music Concierge:

```text
voice → transcript → PlaybackIntent → queue → MIDI
```

The speech layer should never bypass intent validation or directly control MIDI.

Possible implementations may include browser speech features, a local speech engine, or an external assistant integration. The core application should remain agnostic.

## Guest jukebox / QR requests

A QR code on the appliance could open a limited household/party request interface.

Guests may:

- browse a curated visible library;
- search;
- request a song;
- vote/like requests if enabled.

Guests may not:

- change device configuration;
- edit the library;
- configure AI/cloud credentials;
- change backup settings;
- gain shell/system access.

Requests should normally enter a queue rather than interrupting the active song.

## Physical appliance controls

Optional controls can make the installation feel more like purpose-built musical hardware:

- illuminated Play/Pause button
- rotary encoder for volume/navigation
- Stop/Panic button
- status light

They should call the same server command layer as web clients.

## External amplification

Many candidate keyboards expose headphone or line-level audio output. OpenOrchestrion can therefore begin with built-in speakers and later use powered speakers or other amplification without changing the MIDI architecture.

Audio routing/mixing becomes more important when two sound engines are used. A future build may combine their analog outputs through a compact mixer or audio interface if the physical installation benefits from centralized amplification.

## Multiple sound engines

A second engine enables:

- polyphony load distribution
- manufacturer-specific tone preferences
- true two-piano playback
- dueling-piano arrangements
- spatial/antiphonal playback
- redundancy/fallback

Additional devices can use the same profile/routing abstraction.

## Distributed rooms

Future remote endpoints can place sound engines in different rooms.

Do not stream each live MIDI event across ordinary Wi-Fi as the primary timing mechanism. Preferred architecture:

1. pre-stage the complete MIDI asset at each endpoint;
2. synchronize endpoint clocks;
3. send a future start time and routing plan;
4. sequence locally at each endpoint.

This is effectively a specialized multi-room music system for MIDI-rendered instruments.

## Spatial / antiphonal arrangements

With physically separated devices, an arrangement may deliberately assign musical roles by location:

```text
left engine  → piano / violins
right engine → cello / bass / brass
```

Room acoustics and speed-of-sound delay then become part of calibration. This is an artistic extension, not an MVP requirement.

## AI Librarian

AI can assist with library curation:

- normalize composer/title names;
- suggest genres, moods, themes, and era;
- estimate familiarity/background-music suitability;
- flag likely duplicates;
- suggest station tags.

Objective MIDI facts remain deterministic and AI suggestions retain provenance.

## AI Arranger

A later experimental arranger may interpret requests such as:

- “Make this piano only.”
- “Put piano on the Yamaha and the orchestra on the Casio.”
- “Turn this into two pianos.”
- “Make the two keyboards trade verses.”

Arrangement mutation is deliberately later than selection because it changes musical content and requires stronger validation.

## Software-synth fallback

The project currently favors hardware sound engines because they make inexpensive keyboards useful as self-contained appliances. A future software synthesizer can be another implementation of the same destination abstraction for:

- testing without physical hardware;
- fallback when a device is unavailable;
- sounds unavailable on attached hardware;
- headless/distributed endpoints.

This should complement, not undermine, the hardware-neutral routing model.

## Publication / community

Useful public milestones include:

- reference-build photos and enclosure files;
- video of a natural-language request turning into physical keyboard playback;
- documented CT-X700 validation;
- two-device synchronization demo;
- Mozart/two-piano demo;
- purpose-built dueling-piano demo;
- contributor-maintained hardware profiles;
- curated verified-open starter music catalog;
- GitHub Pages documentation/demo site.

A possible article framing remains:

> **I Wanted a Player Piano. I Ended Up Building a Networked MIDI Orchestra.**
