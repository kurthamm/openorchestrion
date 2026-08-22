# Durable Play History

OpenOrchestrion keeps listening history **separate from the rebuildable music catalog**.

`catalog.db` can be deleted and regenerated from durable MIDI sidecars. Listening history is different: it records household behavior that cannot be reconstructed from the MIDI library itself. It therefore lives in its own durable runtime database, normally:

```text
var/history.db
```

This database belongs in application-data backup and restore.

## Why queued is not played

A Smart Station may queue many tracks that the listener never hears. OpenOrchestrion therefore distinguishes these states:

```text
queued
  ↓
started
  ↓
substantially_played
  ↓
completed
```

A started track may instead terminate as:

```text
skipped
failed
```

A track does **not** enter no-repeat/history calculations merely because it was queued or started.

## Substantial-listen threshold

A track earns history/no-repeat credit when actual listening reaches:

```text
min(track duration, min(60 seconds, max(15 seconds, 50% of track duration)))
```

Examples:

| Track duration | Substantial threshold |
| ---: | ---: |
| 10 seconds | 10 seconds |
| 20 seconds | 15 seconds |
| 60 seconds | 30 seconds |
| 120 seconds | 60 seconds |
| 300 seconds | 60 seconds |

If duration is unknown, the threshold is 60 seconds.

This prevents a five-second skip from poisoning a 30-day no-repeat window while still treating a meaningful partial listen as a real play. A completed track always counts.

## Event log plus summary state

The history database contains two layers:

### `play_events`

Meaningful append-only lifecycle events:

- `queued`
- `started`
- `substantially_played`
- `completed`
- `skipped`
- `failed`

High-frequency progress ticks are **not** appended as events. The runtime updates the current played-seconds value and writes a single `substantially_played` event when the threshold is crossed.

### `play_attempts`

Current/summary state for each attempted playback:

- asset/composition IDs
- original track duration
- queued/start/substantial/end timestamps
- final status
- actual seconds played
- failure detail when applicable

The event rows preserve the important lifecycle transitions while the summary table makes history queries inexpensive.

## CLI

Initialize a history database:

```bash
openorchestrion-history var/history.db init
```

Create a queued play attempt:

```bash
openorchestrion-history var/history.db queue \
  --asset-id sha256:example \
  --composition-id composition:example \
  --duration 240
```

The command returns a `play_id`. A future playback state machine will call the same Python API directly rather than shelling out.

Lifecycle examples:

```bash
openorchestrion-history var/history.db start PLAY_ID
openorchestrion-history var/history.db progress PLAY_ID 45
openorchestrion-history var/history.db progress PLAY_ID 60
openorchestrion-history var/history.db complete PLAY_ID --seconds 240
```

A skip or failure can also be recorded:

```bash
openorchestrion-history var/history.db skip PLAY_ID --seconds 12
openorchestrion-history var/history.db fail PLAY_ID --seconds 5 --error "MIDI device disconnected"
```

## No-repeat windows

Query recent substantially played assets/compositions:

```bash
openorchestrion-history var/history.db recent --days 30
```

The Python helper `apply_no_repeat_window()` merges those IDs into `StationConstraints.recent_asset_ids` and `recent_composition_ids`.

Conceptually:

```python
constraints = apply_no_repeat_window(
    StationConstraints(),
    "var/history.db",
    days=intent.repeat_window_days or 30,
)
queue = build_station(
    "var/library/catalog.db",
    intent,
    constraints=constraints,
)
```

This means no-repeat behavior remains deterministic and downstream of AI.

## History summaries

The history service can report, per asset:

- qualifying play count
- last substantially played timestamp
- total listened seconds
- completion count
- skips that occurred only after substantial listening

It also provides `rank_by_staleness()` so never-played material sorts ahead of older plays, which is the foundation for stations such as:

> Something I haven't heard recently

and for future rarity/discovery weighting.

## Persistence and rebuild boundaries

```text
Durable MIDI sidecars ──rebuild──▶ catalog.db
                                   (disposable)

Playback events ─────────────────▶ history.db
                                   (durable)
```

Rebuilding `catalog.db` must never touch `history.db`.

The backup plan therefore treats the history database as application data alongside music metadata, station configuration, and other household state.

## Schema versioning

`history.db` records an explicit schema version. A runtime that encounters an unsupported version fails visibly instead of silently interpreting old history incorrectly. Future schema changes should use explicit migrations.

## Future integration

The playback state machine will emit history lifecycle calls automatically. Smart Stations will use the history service for:

- no-repeat windows
- last-played weighting
- rarely-played discovery
- most-played views
- household listening statistics
- "not heard recently" stations

The normal appliance UI does not need to expose the event machinery, but the administration UI should make history summaries and diagnostics inspectable.
