# OpenOrchestrion

**An open-source, local-first MIDI music appliance with a curated music library, saved playlists, smart stations, and a household web interface.**

OpenOrchestrion began with a simple question:

> What would a player piano look like if it were invented today?

A Raspberry Pi maintains a local MIDI library, builds queues and stations, and drives hardware sound engines from one authoritative playback timeline. The household interface centers on browsing and playback; natural-language interpretation exists as an optional backend capability.

The attached keyboard is treated primarily as a MIDI-addressed synthesizer, amplifier, and speaker system. Human key feel is secondary to MIDI receive behavior, sound quality, polyphony, multitimbral capability, program support, reliability, and price.

## Install and try it

Start with [Getting started](docs/getting-started.md) for installation, first music,
keyboard connection and a hardware-free demo. Use [Troubleshooting](docs/troubleshooting.md)
for common problems and [Contributing](CONTRIBUTING.md) for development.
The reference owner's personal library is not included in this public repository.

## Where the project is now

The appliance is running on a Raspberry Pi 5 with a Casio WK-220. The shared
`main` branch includes the listening-room redesign, durable player workflows,
quality-gated library, secured remote-access integration, off-site backup, and
nightly acquisition. Start with [the current developer handoff](docs/developer-handoff.md).

The initial audit retained **5,832 of 25,893 original files**. The first acquisition
run added **29**, giving **5,861 available performances as of September 7, 2026**.
That is a dated deployment snapshot; the live library/API reports subsequent growth.
The 20,061 excluded originals remain archived. See [quality publication](docs/library-quality-publication.md)
and [automatic acquisition](docs/automatic-acquisition.md).

Implemented today:

- robust MIDI import and deterministic analysis;
- SHA-256 content-addressed assets with durable JSON sidecars;
- curated metadata, favorites, bulk tagging, and re-analysis;
- [complete-listening-v2 admission](docs/library-quality-standard.md), reversible quality archives, and admission gating for new imports;
- rebuildable SQLite catalog plus durable listening history;
- evidence-backed rights/provenance and verified-open starter repertoire;
- deterministic Smart Stations with no-repeat, diversity, compatibility, and relaxation diagnostics;
- offline Music Concierge plus optional hosted OpenAI structured intent interpretation;
- server-owned queue, seek, repeat/shuffle/continuous play, sleep timer, saved playlists/stations, restart recovery, and WebSocket state;
- synchronized multi-output routing from one master timeline;
- `SOLO_PIANO`, `MULTI_INSTRUMENT`, `PIANO_DUET`, `TWO_PIANO`, and `DUELING_PIANO` routing semantics;
- non-destructive Original, Piano Only, and General MIDI Override rendering;
- [responsive listening-room UI](docs/web-listening-room.md) with paginated search, favorites, queue and MIDI performance details;
- explicit Playback & devices settings and privileged local configuration;
- optional `openorchestrion.local` discovery via Avahi/mDNS;
- systemd appliance packaging and non-editable wheel smoke tests;
- verified application-data backup/restore, off-site backup, nightly source acquisition, and system-health reporting;
- CI on Python 3.11–3.13 plus repository, schema, rights, generated-MIDI, and wheel contracts.

Recorded physical evidence:

- WK-220 end-to-end checklist reported passed on September 6;
- headless Pi/WK-220 loaded 120-minute software timing run passed on September 7.

Those results belong to the builds named in [the release evidence](docs/single-keyboard-release-2026-09.md).
They do not certify every later build or acoustic timing.

Deferred or unavailable physical evidence:

- physical touchscreen usability and measured MIDI-to-audio timing;
- complementary second-engine validation and MIDI-to-audio latency measurement;
- two-engine acoustic synchronization evidence;
- reference enclosure/BOM;
- hardware photos and demo video.

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the detailed live status.

## The appliance experience

The [listening room](docs/web-listening-room.md) opens with music collections and repertoire to explore. Browse the complete admitted catalog, combine search and filters, save favorites, inspect a performance’s MIDI instruments, and build a queue. A persistent player keeps the session within reach on desktop, tablet and phone.

The current interface deliberately has no AI prompt or assistant panel. The existing Concierge backend remains available for a future, separately designed integration. Browsing, favorites and queue building work without an AI provider or a connected keyboard.

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
- device readiness and explicit settings without a forced setup redirect;
- journald logs;
- `openorchestrion-smoke` post-install verification;
- safe update and uninstall/recovery procedures.

See [docs/appliance-install.md](docs/appliance-install.md).

## Backup and recovery

OpenOrchestrion treats the Pi as replaceable hardware. The application-data backup format contains content-addressed MIDI objects, sidecars, a SQLite-safe history snapshot, and durable playlists/player session state, with exact manifest digests.

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
node .github/scripts/test-web.mjs
```

CI also builds a real wheel, installs it non-editably outside the checkout, boots the appliance with no physical MIDI output, verifies health and packaged web assets, and requires graceful shutdown.

## Publication

The [Pi implementation review](docs/implementation-review.md) records the September 2026
reliability fixes, regression checks, and remaining hardware/deployment validation.

- [OpenOrchestrion v2 white paper](docs/whitepaper/OpenOrchestrion_White_Paper_v2.md)
- [Project site source](site/)
- [Living architecture documentation](docs/README.md)
- [Roadmap](ROADMAP.md)

The publication deliberately distinguishes **implemented software**, **documented compatibility**, and **physical project validation**. Recorded WK-220 and headless Pi measurements are linked above. CT-X700/second-engine validation, enclosure media, and acoustic calibration remain deferred. The public project site is published through GitHub Pages; release-specific deployment verification is recorded in the maintenance PR.

## Licensing

Software in this repository is released under the MIT License unless otherwise noted. Music files are not automatically covered by the software license; bundled MIDI retains its own recorded provenance and rights information.
