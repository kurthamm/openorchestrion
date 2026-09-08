# Current work queue — September 2026

Start from `main` and [the developer handoff](developer-handoff.md). Historical
release documents and roadmap phases are not unchecked implementation backlogs.

## Completed software and publication work

The listening-room redesign, v2 quality curation, instrument/performance details,
saved playlists/stations, queue editing/persistence, playback modes, seek, sleep,
secured tunnel, backups and nightly acquisition are implemented. Maintenance adds
recovery-tested installation, empty-library bootstrap, ZIP inspection/staging,
first-use/troubleshooting guides and two qualified ensemble starter derivatives.

- **#6 — conformance/timing:** 14 fixtures and the benchmark harness are complete.
  The 120-minute headless Pi run is recorded, plus a passing 10-minute Pi-local
  Chromium/Xvfb run with catalog requests and WebSocket connectivity. These are
  software timing measurements; actual two-engine/acoustic tests remain below.
  [Evidence](repository-maintenance.md).
- **#10 — publication:** v2.1 Markdown white paper and public static site describe
  current software and its evidence limits. Pages Actions source is enabled;
  deployment verification accompanies the maintenance PR. Future physical-build
  photos/video supplement rather than withhold current documentation.
- **#64 — repertoire:** starter repertoire grows from 16 to 18 files, with three
  ensemble entries. Two Donizetti movements pass the unchanged quality policy;
  per-file rights, exact program corrections and all ZIP members are recorded.
  [Repertoire review](repertoire-candidate-review.md).

## Remaining physical or owner-deferred work

| Issue | Ready now | Remaining action |
| --- | --- | --- |
| [#1 — CT-X700 proof](https://github.com/kurthamm/openorchestrion/issues/1) | Manufacturer profile and fixture checklist; WK-220 evidence separately recorded | New keyboard unavailable and owner-deferred. Run its own receive/range/program/controller/endurance checks when available. |
| [#8 — enclosure/BOM](https://github.com/kurthamm/openorchestrion/issues/8) | Concrete headless/display BOM, enclosure option and mounting/cabling/serviceability plan in [reference build](reference-build.md) | Fit, cooling and touch-stability validation on the physical display build, plus photographs. No measured enclosure or acoustic results are invented. |
| [#11 — Yamaha engine](https://github.com/kurthamm/openorchestrion/issues/11) | Manufacturer research retained | Optional later expansion; not the current acquisition plan. No purchase or implementation scheduled. |
| [#84 — two-engine orchestra](https://github.com/kurthamm/openorchestrion/issues/84) | Generic routing and future design retained | Owner-deferred until new hardware is available. Validate physical routing and relative acoustic latency before device-specific orchestra behavior. |

AI browser UI and volume-knob synchronization remain outside the current work.
Do not infer arrival dates from old issue text, transfer WK-220 results to another
model, or call a virtual-display test physical touchscreen validation.

## Library counts

The original audit started with **25,893**, retained **5,832**, and archived
**20,061** originals. The first acquisition run added 29, yielding **5,861** at
that release. This is dated deployment history, not the public starter count or
a fixed capacity. The current API reports subsequent additions.
