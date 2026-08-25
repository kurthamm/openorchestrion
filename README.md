# OpenOrchestrion

**An open-source, local-first MIDI music appliance with natural-language selection, smart stations, multi-keyboard routing, and a household web interface.**

OpenOrchestrion began with a simple question:

> What would a player piano look like if it were invented today?

A Raspberry Pi maintains a local MIDI library, interprets requests such as **“recognizable Christmas piano music while we eat for two hours,”** builds an explainable queue, and drives one or more real hardware sound engines from a single authoritative playback timeline.

The attached keyboard is treated primarily as a MIDI-addressed synthesizer, amplifier, and speaker system. Human key feel is secondary to MIDI receive behavior, sound quality, polyphony, multitimbral capability, program support, reliability, and price.

## Where the project is now

The core software architecture is implemented and packaged as a boot-to-appliance system. Current work is shifting toward **physical validation, repertoire breadth, and publication**.

Implemented today:

- robust MIDI import and deterministic analysis;
- SHA-256 content-addressed assets with durable JSON sidecars;
- curated metadata, favorites, bulk tagging, and re-analysis;
- rebuildable SQLite catalog plus durable listening history;
- evidence-backed rights/provenance and verified-open starter repertoire;
- deterministic Smart Stations with no-repeat, diversity, compatibility, and relaxation diagnostics;
- offline Music Concierge plus optional hosted OpenAI structured intent interpretation;
- server-owned queue, transport, scheduler, cleanup, and WebSocket state;
- synchronized multi-output routing from one master timeline;
- `SOLO_PIANO`, `MULTI_INSTRUMENT`, `PIANO_DUET`, `TWO_PIANO`, and `DUELING_PIANO` routing semantics;
- non-destructive Original, Piano Only, and General MIDI Override rendering;
- responsive kiosk/phone/tablet/desktop web UI;
- first-run setup and privileged local configuration;
- optional `openorchestrion.local` discovery via Avahi/mDNS;
- systemd appliance packaging and non-editable wheel smoke tests;
- verified application-data backup/restore with rollback-safe replacement;
- CI on Python 3.11/3.12 plus repository, schema, rights, generated-MIDI, and wheel contracts.

Still pending physical evidence:

- Raspberry Pi 5 loaded scheduler measurements;
- first real keyboard/sound-engine end-to-end validation;
- complementary second-engine validation and MIDI-to-audio latency measurement;
- two-engine acoustic synchronization evidence;
- reference enclosure/BOM;
- hardware photos and demo video.

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the detailed live status.

## The appliance experience

The goal is a household music appliance, not a DAW:

```text
┌──────────────────────────────────────────────────────┐
│                  OpenOrchestrion                     │
│                                                      │
│  What do you want to hear?                           │
│  ┌────────────────────────────────────────────────┐  │
│  │ Recognizable Christmas piano while we eat     │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│                   ▶ Make it happen                   │
└──────────────────────────────────────────────────────┘
```

The same application runs on the attached touchscreen and household browsers. Closing every browser does not stop playback because the backend owns the queue and timeline.

## Architecture

```text
                             Household LAN
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
     Touchscreen             Phone / tablet          Web browser
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  │
                     ┌────────────▼────────────┐
                     │    OpenOrchestrion Pi   │
                     │                         │
                     │ FastAPI + WebSockets    │
                     │ Music Concierge         │
                     │ Smart Stations          │
                     │ Sidecars + SQLite       │
                     │ Server-owned queue      │
                     │ Master MIDI scheduler   │
                     │ Rendering + routing     │
                     └────────────┬────────────┘
                                  │
                        ┌─────────┴─────────┐
                        │                   │
                    MIDI out A          MIDI out B
                        │                   │
                   Sound engine A      Sound engine B
```

One master scheduler drives all directly attached destinations. OpenOrchestrion does not ask two independent players to remain synchronized over the network.

## AI Music Concierge

AI interprets **listening intent**, never MIDI commands.

```text
natural language
      │
      ▼
validated PlaybackIntent
      │
      ▼
Smart Station / catalog
      │
      ▼
server-owned queue
      │
      ▼
rendering + routing + MIDI playback
```

Hosted AI is explicit opt-in and falls back to the deterministic local interpreter. The model receives no MIDI handle, shell, playback engine, arbitrary tool access, or catalog mutation API.

## Smart Stations

`PlaybackIntent` feeds a deterministic selector that works against real indexed assets. It can consider:

- genre, mood, theme, era, composer, instrumentation, and performance type;
- familiarity and energy;
- favorites and quality;
- duration targets;
- device range/polyphony/GM requirements;
- hard include/exclude tags;
- no-repeat listening history;
- composer diversity and discovery/staleness weighting.

Queues include selection reasons and explicit relaxations instead of silently pretending every request was satisfied exactly.

## Non-destructive rendering

A queue may use:

- **Original Arrangement**: preserve source programs, banks, and percussion;
- **Piano Only**: render pitched parts with a selected General MIDI piano program and suppress GM percussion;
- **Instrument Overrides**: preserve the arrangement while forcing selected pitched channels to specific General MIDI programs.

Rendering happens in memory. The stored MIDI bytes, SHA-256 identity, deterministic analysis, sidecar, and catalog metadata do not change.

## Multi-device playback

Stable performance types include:

| Type | Purpose |
| --- | --- |
| `SOLO_PIANO` | expressive piano on one preferred engine |
| `MULTI_INSTRUMENT` | GM/multichannel material routed by capability and instrument family |
| `PIANO_DUET` | four-hands/duet material with separable parts |
| `TWO_PIANO` | independent Piano I and Piano II destinations |
| `DUELING_PIANO` | purpose-built arrangements that exchange roles between devices |
| `DISTRIBUTED` | future coordinated remote endpoints |

The router can use track/channel identity, General MIDI program family, performance type, device capabilities, projected load, role/device preferences, and per-device latency offsets.

## Library and rights

The library separates:

1. deterministic facts derived from immutable MIDI bytes;
2. curated descriptive metadata;
3. provenance and rights evidence;
4. AI enrichment.

`catalog.db` is rebuildable. Sidecars are authoritative.

For publicly bundled music, OpenOrchestrion also separates the rights status of the **underlying composition** from the license/terms of the **specific MIDI file or arrangement**. A public-domain composition does not automatically make a modern MIDI sequencing public domain.

CI audits tracked MIDI across the repository and fails closed when redistribution evidence is missing or inconsistent.

## Raspberry Pi appliance

The reference software path targets Raspberry Pi OS 64-bit and provides:

- `openorchestrion-serve` under systemd;
- headless operation or health-gated Chromium kiosk mode;
- durable state under `/var/lib/openorchestrion`;
- software under `/opt/openorchestrion/venv`;
- local runtime configuration and separate service-only provider secrets;
- optional Avahi/mDNS discovery;
- first-run setup/readiness guidance;
- journald logs;
- `openorchestrion-smoke` post-install verification;
- safe update and uninstall/recovery procedures.

See [docs/appliance-install.md](docs/appliance-install.md).

## Backup and recovery

OpenOrchestrion treats the Pi as replaceable hardware. The application-data backup format contains content-addressed MIDI objects, sidecars, and a SQLite-safe history snapshot, with exact manifest digests.

Restore verifies the archive, rebuilds the disposable catalog before publication, and rejects traversal, unexpected files, symlinks, duplicate members, digest mismatches, malformed sidecars, and corrupt history. Privileged replacement creates a rollback backup and restores the previous state if the new service cannot become healthy.

See [docs/backup-recovery.md](docs/backup-recovery.md).

## Development without MIDI hardware

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
OPENORCHESTRION_VIRTUAL_MIDI=1 openorchestrion-serve
```

Then open the local service in a browser. Virtual MIDI uses the same playback abstraction as physical outputs, so queue, transport, routing, rendering, WebSocket state, and history can be developed before the keyboards are present.

## Tests

```bash
pytest -q
ruff check --select E4,E7,E9,F .
python .github/scripts/validate_repo.py
```

CI also builds a real wheel, installs it non-editably outside the checkout, boots the appliance with no physical MIDI output, verifies health and packaged web assets, and requires graceful shutdown.

## Publication

- [OpenOrchestrion v2 white paper](docs/whitepaper/OpenOrchestrion_White_Paper_v2.md)
- [Project site source](site/)
- [Living architecture documentation](docs/README.md)
- [Roadmap](ROADMAP.md)

The publication deliberately distinguishes **implemented software**, **documented compatibility**, and **physical project validation**. Hardware measurements and demo media will be added after the reference build exists rather than invented in advance.

## Licensing

Software in this repository is released under the MIT License unless otherwise noted. Music files are not automatically covered by the software license; bundled MIDI retains its own recorded provenance and rights information.
