# OpenOrchestrion

## A local-first networked MIDI music appliance

**White Paper v2.0, software architecture edition**  
**Status:** Living document. Software behavior described as implemented is present in the repository. Hardware performance and compatibility claims remain explicitly provisional until physical project validation is completed.

---

## Abstract

OpenOrchestrion asks a deliberately simple question:

> What would a player piano look like if it were invented today?

The answer is not a piano with a roll reader attached. It is a small networked music appliance that understands listening intent, maintains a curated local MIDI library, builds explainable queues, and drives one or more real hardware sound engines from a single authoritative playback timeline.

A Raspberry Pi runs the application. A touchscreen, phone, tablet, or browser provides control. Standard MIDI Files remain local. Natural-language requests are interpreted into a strict `PlaybackIntent`, then deterministic library and station logic decides what real music exists and what is appropriate to play. Playback, timing, routing, history, metadata, and device cleanup are server-owned. Hosted AI is optional and never sits in the MIDI execution path.

The attached keyboard is treated primarily as a MIDI-addressed sound engine with amplification and speakers rather than as a human performance controller. This changes the procurement question. Key feel and physical key count become secondary to MIDI receive behavior, sound quality, polyphony, multitimbral capability, program support, outputs, reliability, and price.

The current software is appliance-ready: it can be installed from a wheel, boot under systemd with no MIDI hardware attached, serve a responsive local web application, maintain a content-addressed library with durable sidecars, generate Smart Stations, use hosted or offline intent interpretation, run a server-owned playback state machine, route one master timeline to multiple outputs, perform non-destructive General MIDI rendering, preserve durable listening history, and create verified application-data backups.

The major remaining evidence is physical rather than architectural: Raspberry Pi timing under real appliance load, end-to-end validation on the selected keyboard sound engines, MIDI-to-audio latency measurement, two-engine acoustic synchronization, and the physical enclosure/BOM.

---

## 1. Design goals

OpenOrchestrion is designed around the experience of a household appliance rather than a workstation application.

The primary goals are:

1. **Simple listening control.** A user should be able to ask for music in ordinary language or browse with normal station/search controls.
2. **Local musical timing.** Internet availability, cloud latency, provider authentication, and browser connection state must not determine whether notes occur on time.
3. **Real hardware sound.** Inexpensive MIDI-capable keyboards and modules can act as self-contained synthesis engines with their own DACs, amplification, and speakers.
4. **Explainable selection.** AI may interpret preferences, but deterministic application logic chooses real assets and can explain relaxations, scoring, and compatibility decisions.
5. **Rebuildable library intelligence.** Durable sidecars remain authoritative while SQLite indexes can be deleted and reconstructed.
6. **Multiple sound engines from one clock.** Two keyboards should not behave like independent players attempting to stay synchronized. They are outputs of one scheduler.
7. **Hardware neutrality.** The software should route by capabilities and profiles rather than by product-name conditionals.
8. **Safe music provenance.** Publicly distributed MIDI must have evidence for both the composition and the specific file/arrangement.
9. **Recoverable appliance operation.** A failed Pi should be replaceable from documented software plus verified backups rather than treated as a precious snowflake installation.
10. **Open-source reproducibility.** Architecture, installation, test strategy, device profiles, decisions, and rights rules live in the repository.

---

## 2. What OpenOrchestrion is not

Several boundaries are intentional.

OpenOrchestrion is **not a DAW**. It does not expose a multitrack editing timeline as the primary household experience.

It is **not an AI MIDI generator with hardware access**. A model does not emit Note On/Off, SysEx, shell commands, filenames, or device instructions. AI interpretation terminates at a validated data structure.

It is **not a cloud streaming MIDI service**. The playable asset exists locally before scheduling begins.

It is **not a browser-owned player**. Closing every browser does not stop the server-owned queue or scheduler.

It is **not a mystery MIDI redistribution project**. A downloadable file is not considered redistributable merely because the composition is old or the source site is public.

---

## 3. Appliance architecture

The reference topology is:

```text
                            Household LAN
                                 |
          +----------------------+----------------------+
          |                      |                      |
     Touch display          Phone / tablet          Browser
          |                      |                      |
          +----------------------+----------------------+
                                 |
                    +------------v-------------+
                    |      OpenOrchestrion      |
                    |        Raspberry Pi       |
                    |                           |
                    | FastAPI + WebSockets      |
                    | Setup / status / UI       |
                    | Music Concierge           |
                    | Smart Stations            |
                    | Sidecars + SQLite         |
                    | Server-owned queue        |
                    | Master MIDI scheduler     |
                    | Rendering + routing       |
                    +------------+--------------+
                                 |
                    +------------+-------------+
                    |                          |
               MIDI output A              MIDI output B
                    |                          |
               Sound engine A             Sound engine B
                    |                          |
                 speakers                    speakers
```

There is one playback process. The process owns queue state, transport state, the master position, MIDI outputs, scheduler timing, cleanup, history events, and WebSocket sequence state.

The browser is a control and visualization surface. It receives snapshots and typed state deltas and can issue validated commands, but it does not derive authoritative queue order or musical position from its own assumptions.

---

## 4. The AI Music Concierge boundary

Natural language is useful because household listening requests are rarely database queries. People say:

- "Play dinner music for about two hours."
- "A little more upbeat."
- "Make it more recognizable."
- "Add Christmas music."
- "More piano."

OpenOrchestrion converts those requests into `PlaybackIntent`, a strict Pydantic model that forbids unknown fields. Intent can include duration, genre, mood, theme, era, composer, instrumentation, performance type, familiarity, energy, inclusion/exclusion tags, no-repeat behavior, device preferences, and routing preferences.

The execution boundary is:

```text
user language
     |
     v
intent interpreter
     |
     v
validated PlaybackIntent
     |
     v
Smart Station / catalog logic
     |
     v
QueueItemSpec
     |
     v
playback + routing
```

A hosted provider receives no playback engine, shell, MIDI port, catalog mutation API, or arbitrary tool access.

### 4.1 Hosted and offline operation

The first hosted adapter uses the OpenAI Responses API with strict structured output. It is explicit opt-in. Merely having an API key on the Pi does not cause requests to leave the appliance.

The public `PlaybackIntent` intentionally contains an open-ended `routing_preferences` map. Strict hosted structured-output schemas require closed object shapes, so the provider boundary uses a private transport model that represents routing preferences as key/value rows and converts them losslessly back into the public model.

If hosted interpretation fails because of configuration, network, timeout, refusal, missing parsed output, or invalid output, the deterministic offline interpreter handles the request. Manual browsing, station execution from an existing intent, queue control, and playback never depend on hosted AI.

### 4.2 Privacy boundary

When hosted AI is enabled, the prompt and current validated intent for a refinement may leave the appliance. The MIDI library, filenames, sidecars, queue, listening history, device list, MIDI events, and audio are not needed for intent interpretation and are not part of that provider contract.

---

## 5. Smart Stations and deterministic selection

The Concierge does not pick filenames. `PlaybackIntent` feeds a deterministic station builder that queries actual indexed assets.

Selection separates hard eligibility from soft preference.

Hard constraints can include:

- redistribution or personal-library policy;
- performance type;
- device note range;
- practical polyphony limits;
- General MIDI or percussion requirements;
- explicit include/exclude tags;
- recent-history exclusions;
- other compatibility limits.

Eligible candidates are then scored using factors such as:

- requested genre, mood, theme, era, composer, or instrumentation;
- familiarity;
- energy;
- favorite status;
- quality grade;
- seeded variation;
- composer diversity;
- energy transition;
- duration fit;
- discovery or staleness weighting.

The queue records why items were selected and any relaxations applied when the exact request could not be satisfied. The goal is not merely deterministic behavior, but behavior that can be inspected and explained.

---

## 6. Library identity and durable metadata

Imported MIDI is content-addressed by SHA-256. The object identity belongs to the immutable bytes, not to a filename entered by a user.

Each asset has a sidecar that separates four categories of information:

1. **File identity and deterministic analysis** derived from the immutable MIDI bytes.
2. **Curated descriptive metadata** such as title, composer, year, genre, mood, themes, instrumentation, quality, familiarity, energy, and tags.
3. **Provenance and rights evidence** describing where the file came from and what claims support redistribution status.
4. **AI enrichment** kept distinct from human-curated descriptive facts.

The sidecar is authoritative. `catalog.db` is a query accelerator and can be deleted and rebuilt.

### 6.1 Metadata editing

Curated metadata can be edited per asset with `openorchestrion-tag` or in bulk using CSV rows keyed by SHA-256. Descriptive facets use normalized free text rather than a globally locked vocabulary because hobbyist collections inevitably contain categories not anticipated by the original schema.

Fields that drive application behavior, such as `performance_type`, remain stable enumerations.

Writes use optimistic revisions plus a per-asset writer lock. The writer validates the resulting sidecar before replacement, uses atomic filesystem replacement, and reconciles the catalog. Curating a title or favorite cannot upgrade rights evidence or overwrite deterministic analysis.

### 6.2 Re-analysis

When analyzer behavior improves, OpenOrchestrion can re-derive deterministic analysis from the immutable MIDI object without re-importing the asset. Re-analysis refuses to overwrite an object whose bytes no longer match its content-address identity.

This mechanism was used to correct sustain-aware peak-polyphony analysis while preserving curation, provenance, and enrichment.

---

## 7. MIDI analysis and practical polyphony

The analyzer records structure needed for both curation and playback compatibility, including:

- duration and tempo behavior;
- tracks and channels;
- Note On/Off activity;
- velocity distribution;
- program and bank requests;
- sustain/controller usage;
- percussion activity;
- note range;
- expressive events;
- SysEx presence;
- peak simultaneous sounding notes.

Peak polyphony is not calculated by blindly incrementing a counter for every Note On. Repeated pitches under a held sustain pedal must not accumulate impossible phantom voices. The current analyzer tracks sounding note occupancy per channel and note, distinguishing keys currently held from notes sustained by the pedal.

The resulting `peak_simultaneous_notes` is a compatibility estimate used by station constraints and device planning. It is still an estimate of MIDI demand, not a guarantee about a manufacturer's internal synthesis architecture or voice-stealing behavior.

---

## 8. Playback state machine

Playback is server-owned and exposes public states:

- `idle`
- `playing`
- `paused`
- `stopped`

Supported transport actions are play/resume, pause, stop, skip, and panic.

The engine owns:

- the current queue and current index;
- authoritative elapsed position;
- auto-advance;
- idempotent command IDs;
- timing and tempo changes;
- output cleanup;
- history transitions;
- WebSocket state publication.

### 8.1 Timing model

The scheduler uses a monotonic clock. A clock protocol allows the production `SystemClock` to be replaced by `ManualClock` in tests, making timing behavior deterministic without sleeping in unit tests.

MIDI timelines are built from merged event timing and honor tempo changes.

The browser does not rely on server wall-clock synchronization for progress display. It anchors a position message at local receipt time and interpolates using the supplied playback rate.

### 8.2 Pause and resume

Resume can prime durable MIDI channel state such as program, controller, pitch-wheel, and aftertouch state before continuing from a later point in the timeline. Held notes are not reconstructed as though the synthesizer had retained physical key state through a pause.

### 8.3 Cleanup and panic

Panic behavior is explicit per output and channel. It releases sustain and sends appropriate all-sound/all-notes-off controller cleanup rather than executing arbitrary imported SysEx. Imported SysEx is suppressed by default.

---

## 9. One master timeline for multiple sound engines

The central multi-device design decision is simple: locally attached keyboards are destinations of one master sequencer.

They are not independent clients playing copies of a file and attempting to remain in sync.

The routing layer can consider:

- track/channel identity;
- General MIDI program family;
- performance type;
- device capabilities;
- preferred instrument families;
- projected keyed-note/polyphony load;
- explicit device preferences;
- role preferences;
- per-device latency offsets.

### 9.1 Performance types

OpenOrchestrion uses stable performance types:

| Type | Meaning |
| --- | --- |
| `SOLO_PIANO` | expressive piano performance |
| `MULTI_INSTRUMENT` | multichannel/ensemble arrangement |
| `PIANO_DUET` | four-hands or duet material with separable roles |
| `TWO_PIANO` | music written for two independent pianos |
| `DUELING_PIANO` | arrangements that exchange roles between devices |
| `DISTRIBUTED` | future coordinated remote endpoints |

Curated `performance_type` is a routing input. Free-text `instrumentation` is descriptive/advisory and is not treated as an executable routing contract.

### 9.2 Instrument-family affinity and load

For general multichannel material, the planner can prefer a sound engine based on requested General MIDI program family and then consider projected load. This allows a Yamaha and Casio, for example, to be used as complementary sound engines rather than simply mirroring the same file.

### 9.3 Device failure

Silent mid-performance reassignment can be musically wrong. If an active required destination disappears, the conservative behavior is to stop the performance and panic remaining outputs instead of silently moving Piano II or a routed part to another engine without user intent.

---

## 10. Per-device latency compensation

Different hardware synthesizers may not convert the same arriving MIDI event to audible sound at exactly the same latency.

OpenOrchestrion supports a configured latency offset per device. The software benchmark separately measures scheduler behavior, while physical validation will measure MIDI-to-audio latency and relative acoustic alignment between real sound engines.

This distinction matters:

- **scheduler jitter/drift** is a software timing property;
- **MIDI-to-audio latency** is a hardware/system property;
- **sound travel time** is an acoustic placement property.

The final two-engine calibration procedure must account for all three rather than blaming every audible offset on Python scheduling.

---

## 11. Non-destructive playback rendering

A MIDI asset can be rendered differently without changing the stored object.

Three queue-time modes are implemented:

### Original Arrangement

Preserve accepted source Bank Select, Program Change, percussion, and arrangement behavior.

### Piano Only

Suppress General MIDI percussion, suppress source program/bank choices on pitched parts, and assign a selected General MIDI piano program.

### Override

Preserve the arrangement while forcing selected pitched MIDI channels to explicit General MIDI programs.

Precedence is:

```text
source arrangement < rendering mode < explicit program override
```

Rendering occurs in memory before routing. Routing therefore sees the sound family that will actually be heard, not merely the source program family.

The browser obtains the canonical 128-program General MIDI vocabulary from the backend rather than embedding a separate name table. Rendering choice is a browser-local preference for the next queue, not a claim about the currently playing server-owned queue.

---

## 12. Responsive household interface

One no-build HTML/CSS/ES-module application serves:

- the reference touchscreen kiosk;
- phones;
- tablets;
- desktop/laptop browsers.

The application includes:

- Listen / Concierge;
- station shortcuts;
- browse/search;
- favorites;
- queue management;
- recent history;
- Now Playing;
- play/pause/stop/skip/panic;
- live progress interpolation;
- device/library/AI degraded state;
- setup/readiness guidance;
- playback rendering controls;
- reconnect and WebSocket sequence-gap recovery.

The frontend intentionally has no Node build requirement, no CDN, and no external runtime resource dependency.

---

## 13. Appliance packaging and first-run setup

The reference deployment is a boot-to-service Raspberry Pi installation.

The production path includes:

- `openorchestrion-serve` as the single Uvicorn/FastAPI process;
- systemd service ownership;
- durable state under `/var/lib/openorchestrion`;
- software under `/opt/openorchestrion/venv`;
- shared non-secret runtime configuration under `/etc/openorchestrion`;
- separate service-readable secret configuration for hosted-provider credentials;
- health-gated Chromium kiosk startup;
- headless mode;
- journald logging;
- post-install smoke checks;
- update behavior that gracefully stops playback before replacing package files.

### 13.1 First-run UI and configuration

The browser setup view reports authoritative readiness for service, MIDI outputs, library indexing, Concierge availability, and next actions.

Security-sensitive configuration remains a local administrator operation rather than an unauthenticated LAN write API. `openorchestrion-configure` can update provider settings and credentials with redaction, atomic file updates, permission preservation, and service restart behavior.

### 13.2 Friendly local discovery

The reference appliance can advertise its configured HTTP service through Avahi/mDNS. An operator may explicitly choose the `openorchestrion` hostname to obtain `openorchestrion.local` on compatible household networks. Discovery failure does not stop playback or the backend.

---

## 14. Durable play history

Listening history is operational data, not a rebuildable catalog projection.

`history.db` records attempts and events such as:

- queued;
- started;
- substantially played;
- completed;
- skipped;
- failed.

A queue entry or a quick start/skip does not automatically count as a meaningful play. Substantial-play thresholds and completion semantics feed no-repeat windows and staleness ranking back into Smart Stations.

Normal service shutdown stops an active performance so a durable history attempt is not stranded as permanently "started."

---

## 15. Backup and recovery

The Pi should be disposable hardware. Durable application data must survive replacement.

OpenOrchestrion has a versioned application-data backup format containing:

- content-addressed MIDI objects;
- their authoritative sidecars;
- a SQLite-safe snapshot of `history.db` when present;
- a manifest with exact size and SHA-256 for each payload.

`catalog.db` is intentionally excluded because it is rebuildable.

Backup creation verifies content identity and sidecar consistency before publication and writes the final archive atomically.

Restore uses a verify-then-publish model. It does not blindly `extractall` a ZIP. It rejects traversal, unexpected members, duplicate paths, symlinks, digest mismatches, malformed sidecars, corrupt history, unsupported versions, and non-empty target races.

The privileged operator workflow can replace existing durable state with a preflight-verified candidate, retain a rollback backup, stop the service only after preparation succeeds, restart and health-check the new state, and restore the prior tree if the new service fails health validation.

Provider secrets and system configuration are not silently embedded in data backups.

---

## 16. Rights and provenance model

OpenOrchestrion separates two questions that are often collapsed incorrectly:

1. What is the copyright/rights status of the underlying musical composition?
2. Under what terms was this specific MIDI file, performance, engraving-derived sequence, or arrangement distributed?

A public-domain composition does not make every modern MIDI sequencing of it public domain.

A `verified-open` file therefore requires evidence that can be revisited. The repository records source reference, composition basis, file license, redistribution status, and attribution when required.

Unknown licenses are unestablished rather than assumed permissive. Personal-use material remains valid for an owner's private library without being allowed into the redistributable starter set.

CI audits Git-tracked MIDI repository-wide so moving a questionable file to another directory cannot bypass the policy.

### 16.1 Starter repertoire

The repository now ships a verified-open starter library built through the same importer, rights, tagging, analysis, and catalog pipeline used by normal libraries.

The current repertoire covers solo piano, ragtime, classical/baroque, seasonal music, and genuine piano-duet material. Chamber/orchestral breadth remains an active curation lane because most current assets are still keyboard-origin material.

The goal is not a huge bundled collection. It is a small collection where every file can answer: what is this, where did these exact bytes come from, what are its terms, and why does the project believe it may redistribute them?

---

## 17. Test and conformance strategy

The software is designed to be testable before hardware exists.

Generated copyright-clean MIDI fixtures cover:

- single note;
- velocity ladder;
- sustain CC64;
- Program Change and Bank Select;
- General MIDI multichannel ensemble;
- channel 10 percussion;
- note range;
- 16/32/48/64-note polyphony stress;
- two-piano split;
- synchronization click;
- long-duration scheduling;
- unsupported/parser-resilience cases.

CI runs stable named checks for lint, Python 3.11, Python 3.12, and repository contracts.

Repository contracts validate schemas, device profiles, generated MIDI analysis/import/catalog behavior, Smart Stations, tracked-music rights policy, and a real non-editable wheel installation.

The wheel test boots the packaged application outside the checkout, with no physical MIDI hardware, verifies the health/UI assets, and requires graceful application shutdown.

---

## 18. Raspberry Pi timing benchmark

The software timing harness measures:

- p95 and p99 scheduler jitter;
- maximum jitter;
- accumulated relative timing error;
- long-run drift;
- simultaneous two-output skew.

Reference thresholds are treated as provisional engineering targets, not universal CI gates on shared virtual runners.

The authoritative hardware evidence requires a controlled Raspberry Pi 5 run with the actual appliance load active: FastAPI, Chromium kiosk where applicable, WebSockets, library operations, and one/two output paths.

The benchmark protocol records environment and thermal/undervoltage information so a result means more than "it sounded fine."

**Status:** benchmark tooling and runbook are implemented. Reference Pi measurements are still pending.

---

## 19. Hardware selection model

The keyboard-as-sound-engine idea changes what "good hardware" means.

A reference device should be evaluated for:

- documented inbound MIDI;
- Linux enumeration behavior;
- velocity response;
- sustain CC64;
- Program Change;
- Bank Select;
- General MIDI or known program behavior;
- multitimbral receive;
- practical polyphony and voice stealing;
- sound quality across useful instrument families;
- built-in amplification/speakers or usable audio outputs;
- reconnect and power-cycle behavior;
- MIDI-to-audio latency;
- acquisition price and availability.

Physical key count is not automatically MIDI receive range. A 61-key keyboard may accept MIDI note numbers outside its physical keybed if the internal implementation supports them.

Manufacturer documentation can establish **documented compatibility**, but project documentation promotes hardware to **project validated** only after physical evidence is captured.

---

## 20. Reference hardware status

The current project has considered several Casio and Yamaha candidates as inexpensive complementary hardware sound engines. The software remains profile-based and does not depend on a particular model name.

The repository includes manufacturer-evidence profiles and hardware-proof issues, but the final reference pair is not yet physically validated by this project.

This paper therefore does not claim measured latency, acoustic synchronization, practical sustained polyphony, or reconnect reliability for a specific keyboard model yet.

Those measurements are publication milestones, not details to invent around the absence of hardware.

---

## 21. Security and trust boundary

The reference backend is intended for a trusted household LAN.

It is not currently an authenticated Internet-facing music service. Operators should not port-forward the appliance HTTP service directly to the public Internet.

Sensitive provider credentials are stored separately from the world-readable runtime configuration used by the kiosk and diagnostics.

Browser first-run setup is intentionally limited. It cannot write arbitrary filesystem paths, system settings, hostnames, shell commands, or secrets.

Restore/replacement of durable state remains a privileged local administration operation rather than an unauthenticated LAN endpoint.

---

## 22. Architecture decisions that shaped the system

The repository records durable architecture decisions as ADRs. Important accepted directions include:

- local-first playback;
- keyboards treated as sound engines;
- AI isolated from MIDI execution;
- one shared responsive web UI;
- sidecars as durable library authority;
- SQLite catalog as rebuildable projection;
- listening history as separate durable runtime state;
- one server-owned playback timeline;
- no-build frontend delivery;
- synchronized routing from one scheduler;
- evidence-based compatibility rather than connector-name assumptions.

These decisions reduce the number of hidden distributed-state problems in what should feel to the household like a simple music box.

---

## 23. Future distributed mode

The current multi-device design is local: one Pi schedules multiple directly attached outputs.

A future distributed OpenOrchestrion mode would need a different contract:

- lightweight remote endpoints;
- pre-staged/cached MIDI assets;
- synchronized clocks;
- coordinated absolute start timestamps;
- room/device groups;
- endpoint health and fallback rules;
- explicit spatial/antiphonal performance profiles.

Event-by-event MIDI over ordinary Wi-Fi is not the intended synchronization strategy. Distributed endpoints should schedule locally from preloaded material after clock synchronization and coordinated start negotiation.

---

## 24. Current implementation status

### Implemented software

- MIDI analyzer and robust importer
- content-addressed assets and durable sidecars
- curated metadata editor and bulk tagging
- re-analysis and catalog reconciliation
- rebuildable SQLite catalog
- evidence-backed rights/provenance model
- verified starter repertoire pipeline
- Smart Stations and explainable selection
- durable no-repeat/listening history
- deterministic offline Concierge
- optional hosted OpenAI Concierge
- server-owned queue and transport
- monotonic scheduler and timing benchmark
- virtual MIDI testing backend
- synchronized multi-output routing
- performance-type and intent routing hints
- non-destructive Original/Piano Only/Override rendering
- responsive kiosk/household browser UI
- first-run setup and local-admin configuration
- friendly LAN discovery
- systemd appliance packaging
- verified backup/restore core and privileged rollback-safe operator workflow
- CI across Python 3.11/3.12 plus repository/wheel contracts

### Active work

- deeper chamber/orchestral verified-open starter repertoire
- publication site and v2 white paper

### Hardware evidence pending

- Raspberry Pi 5 loaded timing run
- first physical keyboard/sound-engine validation
- complementary second-engine validation
- measured relative MIDI-to-audio latency
- two-engine acoustic synchronization
- physical enclosure and BOM
- hardware photos and demo video

---

## 25. Why this architecture is useful beyond player piano nostalgia

The player-piano framing is intentionally approachable, but the architecture addresses a more general problem: how to put modern intent interpretation and household networking in front of deterministic real-time-ish local hardware without making the cloud, browser, or model the source of operational truth.

OpenOrchestrion uses AI where ambiguity is useful and deterministic systems where correctness matters.

It uses SQLite where queryability matters and durable sidecars where recoverability matters.

It uses browsers where access matters and one server-owned process where timing and state ownership matter.

It uses cheap general-purpose keyboards as network-addressable synthesis appliances, extracting more value from hardware that already contains tone generation, DACs, amplification, and speakers.

That combination is the core idea: **a contemporary household music appliance built from ordinary components, with the intelligence at the edge and the music still local.**

---

## 26. Next evidence milestones

The software is now mature enough that the next important questions should be answered with measurements rather than more architecture prose.

1. Install the packaged wheel on the reference Raspberry Pi through the documented systemd path.
2. Run the appliance smoke test with no MIDI hardware and then with the first device attached.
3. Capture Linux MIDI enumeration evidence.
4. Validate Note On/Off, velocity, sustain, Program Change, Bank Select, percussion, note range, dense polyphony, long playback, reconnect, and power-cycle behavior.
5. Run the controlled Pi timing protocol under realistic appliance load.
6. Attach the complementary second sound engine and measure relative MIDI-to-audio latency.
7. Run true two-device and duet material from the one master timeline.
8. Publish the enclosure/BOM and capture photos/video of the reference build.
9. Regenerate publication PDF/DOCX formats from this living v2 Markdown source with measured results replacing pending labels.

---

## Conclusion

OpenOrchestrion began with the image of a player piano and became a small exercise in disciplined systems design.

Natural language should be allowed to be fuzzy. Music selection can be weighted and personal. The web UI can be friendly and ubiquitous. But the queue should have one owner. MIDI timing should stay local. Music identity should be content-addressed. Metadata should survive a database rebuild. Rights claims should carry evidence. Multiple sound engines should follow one timeline. Backups should be verifiable before they replace working state.

The result is a system that aims to feel simpler than the machinery inside it.

That is the point.
