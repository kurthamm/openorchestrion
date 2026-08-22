# Hardware Selection

## Selection principle

OpenOrchestrion is not buying a keyboard for a human performer. It is buying a **MIDI-addressable hardware sound engine with speakers that happens to have keys attached**.

Therefore the normal digital-piano buying hierarchy changes.

## Reference compute platform

The current **Appliance Edition reference build** uses a **Raspberry Pi 5 with 4 GB RAM**.

Four gigabytes is the baseline because the expected workload is modest for this class of computer:

- FastAPI application services
- SQLite library/catalog operations
- MIDI parsing, sequencing, routing, and scheduling
- WebSocket state synchronization
- Chromium kiosk mode
- one or more USB MIDI endpoints
- background library indexing and backup tasks

OpenOrchestrion should not require an 8 GB Pi merely to support hosted AI. AI providers are expected to be remote or pluggable. If a future release attempts substantial local-model inference, its compute/RAM requirements should be evaluated separately rather than silently changing the baseline appliance.

The software shall remain portable to comparable Linux hardware and must avoid unnecessary Raspberry-Pi-specific coupling.

### Reference Pi accessories

The current baseline assumes:

- Raspberry Pi 5, 4 GB
- active cooling appropriate for continuous appliance use
- official-quality USB-C power supply with adequate Pi 5 power budget
- 128 GB high-endurance microSD for the initial build
- optional NVMe storage as a reliability/performance upgrade
- wired Ethernet when convenient, otherwise Wi-Fi
- direct USB MIDI connections to locally attached sound engines where supported

MIDI storage capacity is not a significant driver. Reliability and recoverability matter more than raw disk capacity.

## Attached display strategy

The display is **optional to the architecture but standard in the reference Appliance Edition**.

The current reference choice is a **7-inch touchscreen**. A very small display is intentionally not the default because the UI includes a natural-language Music Concierge, Now Playing information, queue controls, stations, and touch targets. Seven inches provides enough room for a useful appliance interface without turning the installation into a general-purpose monitor.

The attached display must **not** introduce a second application stack. It runs the same responsive OpenOrchestrion web application used by household phones, tablets, and computers, typically through Chromium in kiosk mode pointed at the local service.

```text
                    OpenOrchestrion Web App
                              │
               ┌──────────────┼──────────────┐
               │              │              │
         7-inch kiosk       phone/PWA      browser
```

This means the screen adds enclosure/hardware work, but very little application-maintenance complexity.

### Why keep the display

The attached display gives OpenOrchestrion an appliance identity and permits immediate use without locating a phone or computer. A person can walk up to the installation and request music directly.

Typical local-screen interactions include:

- AI Music Concierge prompt
- Play Something / Surprise Me
- genre/theme/station shortcuts
- Favorites
- Now Playing
- queue
- play, pause, stop, and skip
- basic device/playback status

Advanced administration is intentionally better suited to a household browser:

- MIDI library import and metadata editing
- hardware/device profiles
- routing configuration
- two-device latency calibration
- AI provider configuration
- backup/recovery status
- logs and diagnostics

The local display is therefore the **front door**, not the entire machine room.

## Supported deployment variants

OpenOrchestrion should support the same software in two initial physical configurations.

### Headless Edition

```text
Raspberry Pi + MIDI sound engine(s) + household browser/phone
```

No attached display is required. This is the lowest-cost and simplest installation.

### Appliance Edition (reference build)

```text
Raspberry Pi 5 4 GB + 7-inch touchscreen + MIDI sound engine(s)
```

The Pi boots into the OpenOrchestrion service and Chromium kiosk UI, producing a self-contained household appliance while retaining full remote web control.

Future distributed endpoints may also run without displays.

## Mandatory requirements for a recommended MIDI sound device

- Documented or physically verified **MIDI receive** from host to internal sound engine.
- Incoming Note On / Note Off support.
- Velocity support.
- Sustain (CC64) support.
- Reliable Linux-compatible MIDI transport, preferably class-compliant USB MIDI.
- Internal sound generation and usable audio output.

## Strongly preferred

- General MIDI or similarly predictable program mapping.
- Multitimbral receive.
- Program Change and Bank Select.
- 48 or more voices of polyphony.
- Built-in speakers.
- Line/headphone output for future external amplification.
- Manufacturer-published MIDI implementation documentation.
- Stable model identification over USB.

## Low-priority characteristics for this project

- Weighted action.
- Key feel.
- Hammer simulation.
- Number of physical keys.
- Lesson modes.
- Built-in songs.
- Human-facing arranger UI.

A 61-key model can be preferable to an 88-key model if its internal MIDI engine receives the required note range and has better synthesis, polyphony, connectivity, documentation, or price.

## Polyphony

Expressive piano MIDI with sustain can consume voices quickly. Full arrangements can consume more. Forty-eight voices is a practical baseline target for inexpensive devices; more is better.

Two devices do not create a mathematically guaranteed doubled polyphony number, but split routing can substantially reduce voice stealing by distributing parts across independent synthesis engines.

## Current two-engine acquisition strategy

A second keyboard is most valuable when it provides a complementary sound engine rather than merely duplicating the first. The current target pairing is:

- **Casio CTK-6200**: primary/general ensemble engine, broad Casio sound set, nominal 48-note polyphony, documented inbound MIDI.
- **Yamaha PSR-EW300**: complementary Yamaha engine, nominal 48-note polyphony, documented two-way USB MIDI, GM/XGlite-family sound set.

This pairing deliberately combines two manufacturers. The goal is to compare and route instrument families to whichever engine sounds best while also gaining independent synthesis capacity for two-piano and split-ensemble playback.

The earlier CT-X700 + Yamaha concept remains architecturally valid, but CTK-6200 + PSR-EW300 is the current procurement target.

A routing profile can choose the preferred engine by instrument family after physical listening/validation establishes useful preferences.

## Procurement rule

For used/auction hardware, evaluate **delivered cost**, not bid price alone:

`delivered_cost = bid + shipping + handling + tax + required power supply/adapters`

Because auction devices carry greater risk than tested retail used gear, the target price should retain a meaningful discount relative to known-good used-market pricing.

See also [reference-build.md](reference-build.md) for the current physical baseline and [supported-hardware.md](supported-hardware.md) for MIDI sound-engine candidates.
