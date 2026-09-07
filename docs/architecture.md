# Architecture

## Architectural intent

OpenOrchestrion is a local-first household music appliance. The host computer manages library intelligence, UI, scheduling, MIDI sequencing, and routing. One or more external keyboards/sound modules provide hardware synthesis and audio output.

The architecture intentionally separates **what the user wants**, **what music should be played**, and **how MIDI is rendered**.

```text
User intent
   │
   ├─ menus / stations / search
   └─ natural-language prompt
             │
             ▼
       PlaybackIntent
             │
             ▼
       Library selector
             │
             ▼
        Smart queue
             │
             ▼
      MIDI analyzer/router
             │
      ┌──────┴──────┐
      ▼             ▼
 Sound engine A  Sound engine B
```

## Major components

### Web application

A responsive UI is served locally to the Pi touchscreen and household browsers.
Implemented controls include Now Playing, queue, search, genre/mood/theme filters,
stations, favorites, history, and the Music Concierge prompt. Broader administrative
and browse requirements are tracked separately in the requirements status table.

### API / application service

FastAPI exposes playback/library endpoints and WebSocket state updates. CPU-heavy
station selection and queue preparation run in one separate worker process; blocking
catalog reads run in threads. The worker receives settings/intent and returns data,
never MIDI devices or playback state. One event loop remains the sole playback owner.
Loaded physical timing validation is still required; process isolation is not a
real-time operating-system guarantee.

### AI Music Concierge

Optional provider-backed natural-language interpreter. It converts conversational requests into a validated `PlaybackIntent`. It does not have direct MIDI device access.

### Library service

Indexes MIDI files and metadata in SQLite while treating the filesystem/sidecar metadata as durable library content. Tracks source, license status, structural MIDI characteristics, play history, and user tags.

### MIDI analyzer

Inspects Standard MIDI Files for duration, tracks, channels, program changes, bank selection, percussion, controllers, sustain, note range, and estimated simultaneous voices.

### Master sequencer

Owns the canonical playback timeline. Pause, resume, seek, tempo, queue changes, and synchronized outputs are controlled here.

### Routing engine

Maps tracks/channels/roles to device outputs. Routing may be explicit, device-capability based, or chosen from a profile associated with the arrangement.

### Device profiles

Describe model-independent and model-specific capabilities including:

- MIDI endpoint identity
- receive support
- General MIDI / extended mode support
- multitimbral parts
- maximum polyphony
- note receive range
- controllers
- Program Change / Bank Select support
- program/tone maps
- percussion behavior
- output latency offset
- preferred instrument families
- built-in audio capability

### Backup/recovery

Application data and music are backed up separately from the operating system. A periodic system image or reproducible installation path provides bare-metal recovery.

## Local-first design

Cloud services are optional and deliberately outside the time-critical playback path.

- MIDI files play from local storage.
- Device scheduling occurs locally.
- Internet loss does not stop an active playlist.
- AI failure falls back to deterministic browsing/stations.
- Cloud storage may be used for backup and recovery.

## One master clock

Multiple keyboards connected to one Pi are driven by one master timeline. This avoids attempting to synchronize independent sequencers.

```text
Master event timeline
        │
        ▼
     Router
     /    \
    /      \
Port A    Port B
 +2 ms     0 ms
   │        │
Device A Device B
```

Per-device latency compensation can align audible output when the devices have different MIDI-to-audio processing delays.

## Distributed future

For instruments in separate rooms, OpenOrchestrion should pre-stage the full MIDI asset on each endpoint and send a coordinated future start timestamp. It should not depend on individual musical events arriving over Wi-Fi at precise times.

## Failure principles

- Loss of AI provider: continue with ordinary controls and existing queue.
- Loss of Internet: local playback continues.
- MIDI link disappears: pause and clean up; reconnect can resume a monitor-induced pause. Dispatch errors stop/fail playback. No automatic rerouting is performed.
- Web client disappears: playback continues server-side.
- Pi restart: services auto-start and return to a known safe state.
