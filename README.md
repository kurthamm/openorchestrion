# OpenOrchestrion

**An open-source, networked MIDI music appliance with AI-powered music selection, smart routing, and multi-keyboard support.**

OpenOrchestrion began with a simple question:

> What would a player piano look like if it were invented today?

The answer grew beyond a player piano. OpenOrchestrion uses a Raspberry Pi or similar Linux computer to manage a local MIDI library, understand natural-language requests such as **“play dinner music for two hours”** or **“give me popular Christmas music”**, build an appropriate queue, and send MIDI to one or more hardware sound engines.

The attached keyboard does not need to be played by a person. Its primary role is to provide a reliable MIDI-addressable synthesizer, piano engine, amplification, and speakers. A single instrument can behave like a modern player piano. General MIDI arrangements can turn the same system into a jazz combo, small orchestra, big band, organ, or pop ensemble. Two or more devices can be routed independently for increased polyphony, complementary sound engines, true two-piano repertoire, or synchronized “dueling piano” arrangements.

## The appliance experience

The goal is not to expose Linux, MIDI plumbing, or a DAW. The finished experience should feel like a household music appliance:

```text
┌──────────────────────────────────────────────┐
│               OpenOrchestrion                │
│                                              │
│        What do you want to hear?             │
│  ┌────────────────────────────────────────┐  │
│  │ Popular Christmas music while we eat  │  │
│  └────────────────────────────────────────┘  │
│                                              │
│              ▶ Make it happen                │
└──────────────────────────────────────────────┘
```

The same responsive interface is available on the attached touchscreen, phones, tablets, and computers on the home network.

## AI Music Concierge

Natural language is a first-class control surface. The AI layer interprets intent; it does **not** directly emit MIDI events.

Example conversation:

> **User:** Play dinner music for about two hours.  
> **User:** A little more upbeat.  
> **User:** Make it more recognizable.  
> **User:** Add some Christmas music.  
> **User:** More piano.

The AI converts those requests into a validated structured `PlaybackIntent`. The deterministic OpenOrchestrion library, queue, routing, and playback engines then execute it.

```text
Natural-language request
          │
          ▼
   AI Music Concierge
          │
          ▼
 validated PlaybackIntent
          │
          ▼
     Library query
          │
          ▼
   Smart queue builder
          │
          ▼
 MIDI analyzer / router
          │
     ┌────┴────┐
     ▼         ▼
 Keyboard A  Keyboard B
```

AI is optional. Core browsing, stations, playlists, and MIDI playback must continue to work without an AI provider or Internet connection.

## Project goals

- Turn inexpensive used MIDI-capable keyboards into a polished household music appliance.
- Play expressive solo-piano MIDI and multi-instrument Standard MIDI Files.
- Let a user simply describe what they want to hear in natural language.
- Provide a responsive web interface on the attached display, phone, tablet, or computer.
- Support browsing, search, random play, themes, genres, moods, favorites, smart stations, and play history.
- Keep playback local so Internet access is never required for musical timing.
- Support one or more MIDI sound engines through a hardware-neutral routing layer.
- Support true two-piano, piano-duet, and purpose-built dueling-piano arrangements.
- Maintain clear source and rights metadata for music in the library.
- Make hardware recovery simple through reproducible deployment plus off-device backups.
- Be reproducible by other hobbyists from documented hardware and software components.

## Reference architecture

```text
                             Home LAN
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
     Touch display          Phone / PWA          Web browser
          │                     │                     │
          └─────────────────────┼─────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  OpenOrchestrion Pi   │
                    │                       │
                    │ Web/API + WebSockets  │
                    │ AI intent interpreter │
                    │ Library + SQLite      │
                    │ Queue / station engine│
                    │ Master MIDI timeline  │
                    │ Router / scheduler    │
                    └───────────┬───────────┘
                                │
                      ┌─────────┴─────────┐
                      │                   │
                  USB MIDI A          USB MIDI B
                      │                   │
                 CT-X700            Yamaha / other
                 reference           optional engine
                      │                   │
                   speakers            speakers
```

The Raspberry Pi owns the master playback timeline. Multiple locally connected devices are outputs from the same sequencer, not independent players trying to remain synchronized.

## Current reference hardware: Casio CT-X700

The Casio CT-X700 is the current reference candidate because Casio documents the computer-to-keyboard MIDI path required by this project. Relevant capabilities include:

- USB MIDI connectivity
- General MIDI Level 1 compatibility
- multi-part MIDI receive
- incoming Note On / Note Off and velocity
- Program Change and Bank Select
- sustain and other controller support
- AiX sound generation
- 600 built-in tones
- 48-note maximum polyphony, with lower limits for some tones
- built-in stereo speakers

The project will remain hardware-neutral. A model is not considered compatible merely because it has a USB port or the word “MIDI” in a listing. **Documented MIDI receive is mandatory for recommended hardware.**

## Why physical key count is not the selection criterion

Nobody needs to play the reference keyboard. OpenOrchestrion is effectively buying a **MIDI-addressable hardware sound engine with speakers that happens to have keys attached**.

A 61-key instrument can still reproduce MIDI notes outside the range of its physical keyboard if its internal MIDI implementation accepts those note numbers. Therefore weighted action, key feel, and even 88 physical keys are low-priority characteristics for this project. Sound quality, MIDI receive behavior, multitimbral capability, polyphony, speakers/audio outputs, reliability, and price matter much more.

## Performance modes

| Type | Description |
| --- | --- |
| `SOLO_PIANO` | Expressive piano performance routed to one piano engine |
| `MULTI_INSTRUMENT` | GM or other multichannel arrangement using multiple instrument parts |
| `PIANO_DUET` | Four-hands/duet material whose parts can be separated across devices |
| `TWO_PIANO` | Music written for two independent pianos |
| `DUELING_PIANO` | Arrangements that trade phrases, accompaniment, and solos between two devices |
| `DISTRIBUTED` | Coordinated playback across multiple room endpoints |

## Multi-device routing

A second keyboard is not merely redundancy. It can add usable polyphony, a different manufacturer's sound palette, and real spatial/two-piano possibilities.

```text
Channel 1   Piano        → Yamaha
Channel 2   Bass         → Casio
Channel 3   Strings      → Yamaha
Channel 4   Trumpet      → Casio
Channel 5   Saxophone    → Casio
Channel 10  Drums        → Casio
```

For genuine two-piano repertoire:

```text
Piano I  → Device A
Piano II → Device B
```

Per-device latency offsets allow small MIDI-to-audio differences to be measured and compensated while every device follows one master timeline.

## Music library

The library is more than a directory of `.mid` files. Each performance can carry metadata such as:

- title and composer/artist
- year and era
- genre, mood, and theme
- familiarity/popularity weighting
- performance type
- source and rights status
- duration
- MIDI format, tracks, and channels
- requested programs/instruments
- percussion usage
- sustain/controller usage
- estimated peak polyphony
- device compatibility assessment
- favorites, play count, and last-played timestamp

This supports stations such as:

- relaxing classical with no repeats for 30 days
- ragtime shuffle
- recognizable dinner music
- popular Christmas music
- orchestral Christmas
- two-piano repertoire
- music not heard recently

## Library rights model

OpenOrchestrion separates:

**Verified/Open Library** — public-domain or appropriately licensed files with explicit provenance and license metadata.

**Personal Library** — MIDI files a user imports and is responsible for possessing/using lawfully.

A freely downloadable MIDI arrangement of a copyrighted modern song is not automatically public domain. The public repository will not ship a mystery pile of copyrighted MIDI files.

## Technology direction

- Raspberry Pi 5 or comparable Linux host
- Raspberry Pi OS
- Python 3.11+
- FastAPI
- SQLite
- Mido plus a Linux MIDI backend
- WebSockets for synchronized UI state
- responsive web application / optional PWA
- Chromium kiosk mode for the attached display
- systemd services for appliance startup
- local-first music playback
- optional cloud backup such as Google Drive, never required for live playback
- pluggable AI provider abstraction

## Backup and recovery

The Pi should be disposable hardware. Recovery is based on two layers:

1. frequent backup of application configuration, music, metadata, stations/playlists, and database data;
2. periodic full-system image or a reproducible deployment path for rapid bare-metal recovery.

Cloud storage is appropriate for backup and recovery because MIDI libraries are small. Live MIDI playback should remain local so Wi-Fi, Internet latency, cloud authentication, or provider outages cannot interrupt musical timing.

## Repository map

```text
.
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── PROJECT_STATUS.md
├── ROADMAP.md
├── SECURITY.md
├── docs/
│   ├── architecture.md
│   ├── requirements.md
│   ├── ai-music-concierge.md
│   ├── hardware-selection.md
│   ├── supported-hardware.md
│   ├── midi-library.md
│   ├── multi-device.md
│   ├── backup-recovery.md
│   ├── project-origin.md
│   └── adr/
├── config/
├── schemas/
├── music/
├── src/openorchestrion/
└── tests/
```

## Status

OpenOrchestrion is currently in **architecture / hardware validation / repository bootstrap**. Manufacturer documentation supports the CT-X700 use case; physical reference-build validation is still pending.

See [PROJECT_STATUS.md](PROJECT_STATUS.md) and [ROADMAP.md](ROADMAP.md).

## Licensing

Software in this repository is released under the MIT License unless otherwise noted. Music files are not automatically covered by the software license. Every bundled musical work must carry its own provenance and rights information.
