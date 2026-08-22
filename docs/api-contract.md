# OpenOrchestrion API Contract

**Status:** Draft for agreement. **Owner:** neither lane — changes require both.
**Applies to:** Issue #5 (web UI) and Issue #14 (playback state machine / virtual MIDI).
**Verified against:** `f2a858d`.

This document exists so that the frontend and backend lanes can work in parallel
without inventing two different APIs. It is the coordination mechanism between
contributors who are not in the same room.

**Rule: if you need a shape that is not in this file, add it here in a PR before
you write code that depends on it.** A contract change is a PR that both lanes
review. Discovering a mismatch at merge time is the failure this file prevents.

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

## 2. Current reality (read this before designing against it)

As of `f2a858d`, `src/openorchestrion/app.py` is **unchanged from the first
commit**. It exposes exactly three endpoints:

```
GET  /api/health          -> {"status": "ok"}
GET  /api/status          -> hardcoded literals, including "ai": {"enabled": false}
POST /api/intent/validate -> echoes the posted PlaybackIntent back
```

Everything else the UI needs — catalog search, Smart Stations, play history, the
Music Concierge — is implemented as **Python libraries with CLI entry points and
no HTTP surface at all**. There is no WebSocket.

`/api/status` currently reports `"ai": {"enabled": false}` as a literal even
though the Concierge landed in `f2a858d`. Do not treat the current response as
truth.

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
`rate`, **anchored at the moment the message arrived locally** — typically a
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

If a client sees a `seq` gap, it does not attempt to patch — it reconnects, or
sends `{"type": "state.request_snapshot"}`, and replaces its local state wholesale.

*Why:* on a household appliance, clients sleep, phones lock, Wi-Fi drops. Delta
streams without resync drift silently. Wholesale replacement is simpler than
reconciliation and cannot half-apply.

### D3 — The backend owns the queue; the client never holds an authoritative copy

The client renders the queue from server state and sends mutations. It must not
maintain its own ordering and diff it.

```
POST /api/queue/reorder  { "asset_id": "...", "to_index": 3 }
POST /api/queue/remove   { "asset_id": "..." }
```

Every mutation both returns the resulting queue and broadcasts it over the
WebSocket, so the originating client and all others converge on the same value.

### D4 — Optimistic UI is allowed, but must reconcile and must be reversible

The 7-inch touchscreen needs immediate feedback; waiting for a round trip before
a pause button responds feels broken. So the client may reflect intent
immediately, but:

- it marks that state `pending` until the server confirms,
- it reverts on error or on a contradicting state message,
- it never treats optimistic state as truth for anything else.

Every command accepts a client-generated `command_id` (UUID). The server echoes
it in the resulting state message so the originating client can clear `pending`.
Commands are idempotent by `command_id` — a retry after a dropped connection
does not double-skip a track.

### D5 — Correlation IDs go in the envelope, never in `PlaybackIntent`

`PlaybackIntent` gained `model_config = ConfigDict(extra="forbid")` in `f2a858d`.
Any unknown field is now a `422`. This is deliberate — it stops model
hallucinations becoming executable instructions — and it applies to the UI too.

So: no `client_id`, no `trace_id`, no UI hints inside the intent object. They go
in the request envelope alongside it:

```json
{ "command_id": "8f14e45f-...", "prompt": "dinner music for two hours",
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
a convenience, not durable data — losing it on restart costs the user one extra
sentence, so it deliberately does not go in a database.

### D6 — Degraded states are explicit fields, never absent data

The UI must distinguish "no AI configured" from "AI request failed" from "AI is
thinking". It cannot infer that from a missing key. Every degradable subsystem
reports its own state:

```json
"ai":      { "enabled": true, "provider": "structured-model", "reason": null },
"outputs": { "ready": false, "devices": [], "reason": "no_midi_output" },
"library": { "asset_count": 0, "tagged_count": 0 }
```

Note `ConciergeResult` already carries `fallback_used` and `primary_error`. When
`fallback_used` is `true`, the UI should say so — "answered offline" — rather
than silently presenting a degraded result as a normal one.

---

## 4. REST endpoints

`(#14)` marks endpoints that depend on the playback state machine. They are
**declared with their real success models** and return `not_implemented` until
that lands, so a generated client already knows the shape it will receive — it
is never told that a successful `/api/queue` call returns an error object.

| Method | Path | Backed by | Status |
|---|---|---|---|
| GET | `/api/health` | — | exists |
| GET | `/api/status` | aggregate | stub → real |
| POST | `/api/concierge/ask` | `ai.MusicConcierge.interpret` | stub |
| POST | `/api/stations/preview` | `stations.build_station` | stub |
| GET | `/api/library/search` | `catalog.search_catalog` | stub |
| GET | `/api/library/stats` | `catalog.catalog_stats` | stub |
| GET | `/api/library/assets/{asset_id}` | `catalog` | stub |
| GET | `/api/library/assets/{asset_id}` | `catalog.get_asset` | implemented |
| POST | `/api/library/assets/{asset_id}/favorite` | **blocked — see §6** | blocked |
| GET | `/api/history/recent` | `history.history_summaries` | stub |
| GET | `/api/devices` | `midi.devices.list_output_ports` | stub |
| GET | `/api/queue` | queue state | (#14) |
| POST | `/api/queue` | replace/append from intent | (#14) |
| POST | `/api/queue/reorder`, `/api/queue/remove` | queue state | (#14) |
| POST | `/api/transport/{play,pause,stop,skip,panic}` | transport | (#14) |
| WS | `/api/ws` | state sync | (#14) |

### `POST /api/concierge/ask`

Request:
```json
{ "command_id": "uuid", "session_id": "kitchen-tablet",
  "prompt": "something more upbeat", "current_intent": null }
```

Response — this mirrors `ConciergeResult.to_dict()` exactly, plus the queue
preview the UI needs to render a result:
```json
{ "intent": { "...PlaybackIntent..." },
  "provider": "structured-model",
  "fallback_used": false,
  "primary_error": null,
  "preview": { "...StationQueue.to_dict()..." } }
```

The Concierge is an async LLM call and may take seconds. The UI needs a
"thinking" state; `command_id` correlates the eventual answer to the prompt.
`session_id` maps to a `ConciergeSession`, which already holds `current_intent`
for successive refinements — "a little more upbeat", "more piano".

### `POST /api/stations/preview`

Takes a `PlaybackIntent`, returns `StationQueue.to_dict()` as already produced by
`stations.build_station()` — including `items[].score_breakdown`,
`selected_for`, `relaxations`, and `diagnostics`.

**Render `relaxations`.** When the selector could not honour the request it says
so, and the appliance should pass that on — "I didn't have enough Christmas
music, so I widened it" — rather than silently serving something else.

### `GET /api/library/search`

Query params map 1:1 onto `catalog.search_catalog()`:
`text`, `composer`, `genre` (repeatable), `mood`, `theme`, `performance_type`,
`rights_status`, `min_familiarity`, `max_energy`, `limit` (1–1000).

## 5. WebSocket

Every message in both directions is a typed, discriminated envelope. `type` is a
closed set, not a free string, and each type has a concrete payload model — see
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
| `state.playback` | transport or track change | `PlaybackState` (carries `PositionAnchor`) |
| `state.queue` | queue mutated | `QueueState` |
| `state.devices` | device appears/disappears | `OutputsState` |
| `state.library` | reindex completed | `LibraryCounts` |
| `concierge.result` | async answer ready | `ConciergeResponse` |
| `error` | command rejected | `ErrorBody` |

Client → server types: `state.request_snapshot`, `ping`. **All mutations go over
REST, not the socket** — one code path for commands, one for state. The socket
is read-mostly.

Until #14 lands, `/api/ws` accepts the connection, sends one `error` envelope
with code `not_implemented`, and closes. That is enough for the UI to build and
exercise its reconnect path now, against the envelope shape it will keep.

## 6. Cross-lane blockers

**Favorites in Issue #5 are blocked.** `favorite` lives in the sidecar's
`descriptive_metadata` block, and nothing in the repository writes to that block
(review finding OO-01). Until a metadata writer exists, `POST .../favorite`
cannot persist. The catalog also reports `0 compositions` for any imported
library for the same reason, so browse/search screens will show untitled assets.

The frontend lane should build the favorite control and the browse screens
against fixture data that *does* have titles and genres, and expect the real
library to look empty until OO-01 lands.

**`/api/status` must become real before the UI trusts it** (§2).

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
other malformed request — a bad query parameter, a malformed queue command — is
`request_invalid`. Conflating them sends the user to the wrong screen.

A bare 500 with an HTML body is never returned: an unhandled exception is caught
and re-emitted as `internal_error`, with the real cause logged server-side and
nothing about it disclosed to the client.

---

## 8. How this gets enforced: stubs first

A prose contract drifts. The mechanism that does not drift is **shipping every
endpoint immediately as a stub returning fixture data**, with real Pydantic
response models.

Then:

- FastAPI generates `/openapi.json` from those models automatically.
- The frontend generates a typed client from it and has a running API on day one.
- The backend fills in implementations behind unchanged signatures.
- Neither lane can drift, because the models are the contract.

This is a small PR — response models plus stub handlers — and it should land
**before** either lane goes far. It belongs to neither #5 nor #14; suggest it as
its own issue.

```python
# sketch: src/openorchestrion/api/models.py
class OutputsState(BaseModel):
    ready: bool
    devices: list[str] = Field(default_factory=list)
    reason: str | None = None

class AiState(BaseModel):
    enabled: bool
    provider: str | None = None
    reason: str | None = None

class SystemStatus(BaseModel):
    phase: Literal["bootstrap", "ready", "playing", "degraded"]
    outputs: OutputsState
    ai: AiState
    library: LibraryCounts
```

## 9. Changing this document

1. Open a PR editing this file.
2. Both lanes review.
3. Merge before writing code that depends on the change.

If a change is architectural — a new boundary, a different ownership split —
add an ADR under `docs/adr/` in the same PR, per the existing project rule.
