# OpenOrchestrion API Contract

**Status:** Accepted baseline for Issues #5 and #14. **Owner:** shared by the UI and playback lanes.
**Applies to:** Issue #5 (web UI) and Issue #14 (playback state machine / virtual MIDI).

This document exists so that the frontend and backend lanes can work in parallel
without inventing two different APIs. It is the coordination mechanism between
contributors and between implementation phases.

**Rule: if you need a shape that is not in this file, add it here in a PR before
you write code that depends on it.** A contract change is a reviewable PR.
Discovering a mismatch at merge time is the failure this file prevents.

---

## 1. Ground rules

These restate project rules that already exist; they are here so the contract is
readable on its own.

- The backend is the source of truth for playback state, queue, history, MIDI
  timing, and AI interpretation. The frontend renders state and sends commands.
- The frontend never computes selection, scoring, no-repeat windows, or MIDI
  timing. Those live in `stations.py`, `history.py`, `catalog.py`, `analyzer.py`.
- AI produces a validated `PlaybackIntent`. It never emits MIDI, SysEx, shell
  commands, or hardware instructions.
- No keyboard model appears in application logic. Device behaviour comes from
  device profiles.

## 2. Baseline this contract replaced

Before PR #15, `src/openorchestrion/app.py` exposed only three development
endpoints:

```
GET  /api/health          -> {"status": "ok"}
GET  /api/status          -> hardcoded literals
POST /api/intent/validate -> echoes the posted PlaybackIntent back
```

The catalog, Smart Stations, play history, and Music Concierge already existed
as Python libraries and CLIs, but had no coherent HTTP surface and there was no
WebSocket state contract. PR #15 establishes that missing seam. The playback
endpoints remain declared-but-pending until Issue #14 fills them in.

## 3. Decisions that otherwise get made twice

This is the important section. Each of these is a choice both lanes would
otherwise make independently and differently.

### D1 — Position is anchored at client receipt, not at server time

The server does **not** push position every second. It pushes a position anchor
whenever playback state changes:

```json
{ "position_ms": 41200, "duration_ms": 187000,
  "rate": 1.0, "server_time": "2026-08-22T14:31:07.412Z" }
```

The client renders a smooth progress bar by interpolating from `position_ms` at
`rate`, **anchored at the moment the message arrived locally**, typically a
`performance.now()` reading taken in the message handler.

**The client must not subtract `server_time` from its own clock.** Browser and
appliance clocks are independent and routinely differ by seconds; a phone that
has not synced NTP can be minutes out. Subtracting one from the other produces
a progress bar that starts in the wrong place or runs backwards. `server_time`
exists for ordering and diagnostics only, and the field carries that warning in
its OpenAPI description so it is hard to misuse by accident.

When `rate` is `0.0` (paused) the client stops advancing. Every state change
re-anchors, so interpolation error never accumulates beyond one message
interval.

*Why not push at 1 Hz:* it is needless traffic to every connected client on a
Pi, and it produces a visibly stuttering bar on the 7-inch display.

### D2 — Reconnect gets a full snapshot; sequence numbers detect gaps

Every WebSocket message carries a monotonically increasing `seq`. On connect the
server immediately sends `state.snapshot` containing complete state. Subsequent
messages are deltas.

If a client sees a `seq` gap, it does not attempt to patch. It reconnects, or
sends `{"type": "state.request_snapshot"}`, and replaces its local state wholesale.

*Why:* on a household appliance, clients sleep, phones lock, and Wi-Fi drops.
Delta streams without resync drift silently. Wholesale replacement is simpler
than reconciliation and cannot half-apply.

### D3 — The backend owns the queue; the client never holds an authoritative copy

The client renders the queue from server state and sends mutations. It must not
maintain its own ordering and diff it.

```
POST /api/queue/reorder
POST /api/queue/remove
```

Every mutation returns the resulting queue and broadcasts it over the WebSocket,
so the originating client and all others converge on the same value.

### D4 — Optimistic UI is allowed, but must reconcile and must be reversible

The 7-inch touchscreen needs immediate feedback; waiting for a round trip before
a pause button responds feels broken. So the client may reflect intent
immediately, but:

- it marks that state `pending` until the server confirms;
- it reverts on error or on a contradicting state message;
- it never treats optimistic state as truth for anything else.

Every mutation command accepts an optional client-generated `command_id` UUID.
The server echoes it in the resulting state so the originating client can clear
its `pending` flag. Commands are idempotent by `command_id`; a retry after a
dropped connection must not double-skip a track.

The Pydantic request models use the actual `UUID` type, so OpenAPI publishes
`format: uuid` and malformed identifiers fail request validation before reaching
the playback engine.

### D5 — Correlation IDs go in the envelope, never in `PlaybackIntent`

`PlaybackIntent` uses `extra="forbid"`. Unknown fields are rejected. This is
deliberate: it stops model hallucinations becoming executable instructions and
keeps UI metadata out of the deterministic intent object.

So: no `client_id`, no `trace_id`, no UI hints inside the intent object. They go
in the request envelope alongside it:

```json
{ "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71",
  "prompt": "dinner music for two hours",
  "session_id": "kitchen-tablet", "current_intent": null }
```

`session_id` is separate from `command_id` and does more than correlate. It
names a **server-side Concierge conversation**, so "a little more upbeat"
refines the previous turn instead of starting over, and every surface in the
house sharing an id sees the same conversation.

- With `session_id`: the turn builds on that session's remembered intent.
- With `session_id` **and** an explicit `current_intent`: the explicit one wins,
  which lets a client resync after losing its own state.
- Without `session_id`: the call is stateless and only `current_intent` applies.

Sessions are in-memory and bounded (LRU, 64 by default). Conversation state is
a convenience, not durable data. Losing it on restart costs the user one extra
sentence, so it deliberately does not go in a database.

### D6 — Degraded states are explicit fields, never absent data

The UI must distinguish "no provider configured" from "AI request failed" from
"AI is thinking". It cannot infer that from a missing key. Every degradable
subsystem reports its own state:

```json
{
  "ai": {"enabled": true, "provider": "deterministic-fallback",
         "reason": "no_provider_configured_using_offline_interpreter"},
  "outputs": {"ready": false, "devices": [], "reason": "no_midi_output"},
  "library": {"indexed": false, "assets": 0, "compositions": 0,
              "genres": 0, "moods": 0, "themes": 0}
}
```

`ConciergeResult` also carries `fallback_used` and `primary_error`. When
`fallback_used` is `true`, the UI should say so, for example "answered offline",
rather than silently presenting a degraded result as a normal one.

---

## 4. REST endpoints

`(#14)` marks endpoints that depend on the playback state machine. They are
**declared with their real success models** and return `not_implemented` until
that lands, so a generated client already knows the shape it will receive. It is
never told that a successful `/api/queue` call returns an error object.

| Method | Path | Backed by | Status |
|---|---|---|---|
| GET | `/api/health` | — | implemented |
| GET | `/api/status` | aggregate | implemented, playback fields become real in #14 |
| POST | `/api/concierge/ask` | `ai.MusicConcierge.interpret` | implemented |
| POST | `/api/stations/preview` | `stations.build_station` | implemented |
| GET | `/api/library/search` | `catalog.search_catalog` | implemented |
| GET | `/api/library/stats` | `catalog.catalog_stats` | implemented |
| GET | `/api/library/assets/{asset_id}` | `catalog.get_asset` | implemented |
| POST | `/api/library/assets/{asset_id}/favorite` | metadata writer | blocked, see §6 |
| GET | `/api/history/recent` | `history.history_summaries` | implemented |
| GET | `/api/devices` | `midi.devices.list_output_ports` | implemented |
| GET | `/api/queue` | queue state | (#14) |
| POST | `/api/queue` | replace/append from intent or assets | (#14) |
| POST | `/api/queue/reorder`, `/api/queue/remove` | queue state | (#14) |
| POST | `/api/transport/{play,pause,stop,skip,panic}` | transport | (#14) |
| WS | `/api/ws` | state sync | (#14) |

### `POST /api/concierge/ask`

Request:

```json
{ "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71",
  "session_id": "kitchen-tablet",
  "prompt": "something more upbeat", "current_intent": null }
```

Response mirrors `ConciergeResult.to_dict()` plus the queue preview the UI needs
to render a result:

```json
{ "intent": { "...PlaybackIntent..." },
  "provider": "structured-model",
  "fallback_used": false,
  "primary_error": null,
  "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71",
  "preview": { "...StationQueue..." } }
```

The Concierge is an async model call and may take seconds. The UI needs a
"thinking" state; `command_id` correlates the eventual answer to the prompt.
`session_id` maps to a `ConciergeSession`, which holds `current_intent` for
successive refinements such as "a little more upbeat" and "more piano".

### `POST /api/stations/preview`

Takes a `PlaybackIntent`, returns `StationQueue.to_dict()` as already produced by
`stations.build_station()`, including `items[].score_breakdown`, `selected_for`,
`relaxations`, and `diagnostics`.

**Render `relaxations`.** When the selector could not honour the request it says
so. The appliance should pass that on rather than silently serving something
else.

### `GET /api/library/search`

Query params map 1:1 onto `catalog.search_catalog()`:
`text`, `composer`, `genre` (repeatable), `mood`, `theme`, `performance_type`,
`rights_status`, `min_familiarity`, `max_energy`, `limit` (1–1000).

### Queue and transport command bodies

`POST /api/queue` accepts **exactly one** queue source. An empty request and a
request containing both sources are `request_invalid`.

Intent source:

```json
{ "mode": "replace",
  "intent": { "themes": ["dinner"], "energy": "low" },
  "seed": 42, "max_tracks": 25,
  "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71" }
```

Explicit asset source:

```json
{ "mode": "append",
  "asset_ids": ["sha256:...", "sha256:..."],
  "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71" }
```

Queue mutations are:

```json
POST /api/queue/reorder
{ "asset_id": "sha256:...", "to_index": 3,
  "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71" }

POST /api/queue/remove
{ "asset_id": "sha256:...",
  "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71" }
```

Transport actions accept an optional body containing only the idempotency token:

```json
POST /api/transport/skip
{ "command_id": "8f14e45f-4b3a-4a66-9ec0-5d6d6f72ad71" }
```

Every queue mutation returns `QueueState`; every transport mutation returns
`PlaybackState`. While #14 is pending, the same routes return a typed 501
`ErrorResponse`.

## 5. WebSocket

Every server message is a typed, discriminated envelope. `type` is a closed set,
not a free string, and each server-to-client type has a concrete payload model in
`api/models.py`.

```json
{ "type": "state.snapshot", "seq": 41,
  "ts": "2026-08-22T14:31:07.412Z", "payload": { } }
```

`seq` increases monotonically; a gap tells the client to resync rather than
patch.

| Type | When | Payload model |
|---|---|---|
| `state.snapshot` | on connect, on resync request | `SnapshotPayload` — status + playback + queue |
| `state.playback` | transport or track change | `PlaybackState` carrying `PositionAnchor` |
| `state.queue` | queue mutated | `QueueState` |
| `state.devices` | device appears/disappears | `OutputsState` |
| `state.library` | reindex completed | `LibraryCounts` |
| `concierge.result` | async answer ready | `ConciergeResponse` |
| `error` | command rejected | `ErrorBody` |

Client-to-server control is intentionally tiny: `state.request_snapshot` and
`ping`. All mutations go over REST, not the socket. One code path handles
commands; the socket is read-mostly state distribution.

Until #14 lands, `/api/ws` accepts the connection, sends one `error` envelope
with code `not_implemented`, and closes. That is enough for the UI to build and
exercise its reconnect path now, against the envelope shape it will keep.

## 6. Cross-lane blockers

**Favorites in Issue #5 are blocked.** `favorite` lives in the sidecar's
`descriptive_metadata` block, and nothing in the repository writes to that block
(review finding OO-01). Until a metadata writer exists, `POST .../favorite`
cannot persist. The frontend may build the control against the published shape,
but must render the 501 state rather than pretending persistence succeeded.

Browse/search can also be sparse until descriptive metadata is populated. The
frontend should handle untitled or lightly tagged assets gracefully instead of
assuming all imported MIDI already has curated metadata.

## 7. Errors

One envelope, with a stable machine-readable `code` the UI can switch on.

```json
{ "error": { "code": "intent_invalid",
             "message": "duration_minutes must be between 1 and 1440",
             "detail": { "field": "duration_minutes" } } }
```

Codes: `intent_invalid`, `request_invalid`, `concierge_unavailable`,
`library_empty`, `asset_not_found`, `no_midi_output`, `transport_conflict`,
`not_implemented`, `internal_error`.

`intent_invalid` is reserved for failures **inside a PlaybackIntent**, so the UI
can send the user back to the Concierge surface with the offending field. Any
other malformed request, such as a bad query parameter, malformed UUID, or
malformed queue command, is `request_invalid`. Conflating them sends the user to
the wrong screen.

A bare 500 with an HTML body is never returned. An unhandled exception is caught
and re-emitted as `internal_error`, with the real cause logged server-side and
nothing about it disclosed to the client.

---

## 8. How this gets enforced

The Pydantic request/response models in `src/openorchestrion/api/models.py` are
the executable contract. FastAPI derives `/openapi.json` from them, and API tests
assert both the success and interim-error schemas for pending playback routes.

PR #15 establishes the complete surface before Issue #14 fills in playback:

- existing domain services are exposed behind typed HTTP responses;
- #14 routes publish their eventual success models now and return typed 501s;
- request validation rejects ambiguous queue sources and malformed UUIDs;
- WebSocket server messages have discriminated payload types;
- the frontend can generate a client from `/openapi.json` without guessing.

Future contract changes update the models, this document, and contract tests in
the same PR before either lane writes code against the new shape.

## 9. Changing this document

1. Open a PR editing this file and the corresponding Pydantic models/tests.
2. Review the effect on both Issue #5 and Issue #14.
3. Merge before writing code that depends on the change.

If a change is architectural, such as a new ownership boundary, add an ADR under
`docs/adr/` in the same PR per the existing project rule.
