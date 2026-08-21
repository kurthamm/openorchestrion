# OpenOrchestrion Reference Build

This document defines the current physical baseline for a reproducible OpenOrchestrion installation. It is a **reference**, not a permanent hardware lock-in.

## Reference Appliance Edition

| Component | Current baseline |
| --- | --- |
| Host | Raspberry Pi 5, 4 GB RAM |
| Display | 7-inch touchscreen |
| OS | Raspberry Pi OS, 64-bit |
| Cooling | Active cooling suitable for continuous operation |
| Storage | 128 GB high-endurance microSD initially; NVMe optional |
| Network | Ethernet preferred when convenient; Wi-Fi supported |
| MIDI | Direct USB MIDI to compatible sound engine(s) when available |
| Local UI | Chromium kiosk mode using the OpenOrchestrion web application |
| Remote UI | Same responsive application from phone, tablet, or computer |
| Reference sound engine | Casio CT-X700 candidate pending physical project validation |
| Optional second engine | Yamaha PSR-EW310/EW300/E363 class candidate |

## Why Raspberry Pi 5 4 GB

The reference system is an appliance controller, not a general-purpose AI workstation. Its primary workloads are local web/API services, SQLite, MIDI scheduling and routing, library analysis, WebSockets, and one kiosk browser. Those tasks do not justify making 8 GB RAM a baseline requirement.

The project should revisit host sizing if future features introduce heavyweight local inference, audio synthesis, or other materially different workloads.

## Why retain the attached display

The display is not required for OpenOrchestrion to function, but it is part of the reference appliance experience.

Without a display, the system is still fully usable from household browsers. With the display, it becomes self-contained: someone can walk up to the instrument and immediately request music without finding another device.

The key architectural rule is that the attached display **does not get its own dedicated UI application**. It renders the same responsive web UI used remotely.

```text
                    One OpenOrchestrion UI
                             │
              ┌──────────────┼──────────────┐
              │              │              │
          kiosk screen     phone/PWA      browser
```

This prevents the attached screen from becoming a large software-maintenance burden.

## Why 7 inches

The local UI must comfortably support:

- a natural-language “What do you want to hear?” prompt
- Now Playing
- prominent transport controls
- station/theme shortcuts
- queue visibility
- basic device status

A very small display saves little in the overall installation while making text input and touch controls unnecessarily cramped. Seven inches is the current baseline compromise between a compact appliance and a usable touch interface.

Larger displays may be used, and headless operation remains supported.

## Local UI versus administration UI

The same web application can present different depth depending on task and viewport.

### Local appliance screen

Optimize for immediate listening:

- Music Concierge
- Play Something
- Surprise Me
- genres/themes/stations
- Favorites
- Now Playing
- queue
- play/pause/stop/skip
- simple playback/device status

### Remote administration

Optimize for configuration and maintenance:

- MIDI import
- metadata editing
- device profiles
- channel/track routing
- multi-device latency calibration
- AI provider settings
- backup and recovery
- logs
- diagnostics

This is a product-design distinction, not a requirement for separate front-end codebases.

## Headless Edition

A display-free installation is a supported first-class variant:

```text
Raspberry Pi
    │
    ├── MIDI sound engine A
    ├── MIDI sound engine B (optional)
    └── home network → browser / PWA
```

The Headless Edition is useful for lower-cost builds, hidden installations, and future distributed room endpoints.

## Appliance Edition

The reference installation adds the touchscreen:

```text
                 ┌──────────────────┐
                 │ 7-inch display   │
                 │ OpenOrchestrion  │
                 └────────┬─────────┘
                          │ localhost
                    ┌─────▼─────┐
                    │ Pi 5 4 GB │
                    └─────┬─────┘
                          │
                   ┌──────┴──────┐
                   │             │
                USB MIDI      USB MIDI
                   │             │
              Engine A       Engine B
```

## Storage philosophy

MIDI files are small. A large storage device is not necessary merely to hold the library. The design therefore prioritizes:

1. storage reliability;
2. simple backup;
3. recoverability;
4. sufficient room for the OS, logs, artwork, metadata, and future expansion.

A 128 GB high-endurance microSD is sufficient for the initial reference build. NVMe is an optional upgrade if the builder wants more robust long-term appliance storage.

## AI and hardware sizing

The AI Music Concierge is provider-neutral and optional. Hosted AI should not force additional local memory requirements. If local AI is later supported, it should be treated as a separately documented deployment profile with its own compute requirements.

## Design status

This reference build is a design baseline. Hardware should be promoted to “project validated” only after physical testing is completed and recorded in the supported-hardware documentation.
