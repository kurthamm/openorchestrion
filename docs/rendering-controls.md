# Browser playback rendering controls

OpenOrchestrion can render an immutable MIDI asset differently at playback time without changing the stored file, its SHA-256 identity, deterministic analysis, sidecar metadata, or catalog record. The playback/rendering domain and public queue request were implemented before the browser controls; this document describes the household UI that now uses that stable boundary.

## Listen control

The Listen screen includes a compact **Sound for next queue** control. Its default is **Original arrangement**. The selector is browser-local preference, not authoritative playback state. It applies when this browser next creates or replaces a queue, whether that queue comes from:

- a Concierge request;
- a station shortcut;
- a preview's **Play this** action; or
- a manual **Play** action in Browse.

The preference is kept in browser local storage for convenience. It is not durable library metadata and it does not claim that an already-playing queue is using the same policy. Another phone or tablet can replace the server-owned queue independently.

## Modes

### Original arrangement

Preserves the source arrangement. The browser omits the optional `rendering` field entirely, preserving the pre-rendering queue request shape.

### Piano only

Suppresses General MIDI percussion and source program/bank choices for pitched parts, then renders them with the selected General MIDI piano program. The browser offers only the eight GM piano programs that the backend publishes.

### Instrument overrides

Keeps the arrangement but lets the user force selected pitched MIDI channels to specific General MIDI programs. Channels are shown to people as 1 through 16, while the API remains MIDI-native 0 through 15. Human/GM channel 10 is percussion, corresponding to API channel 9, and is never offered as an override target.

At least one override is required before an Override queue can be created. Duplicate channel rows are prevented in the editor and normalized browser preference data also rejects duplicates/percussion targets before a request is built.

## One General MIDI vocabulary

The browser does not carry a second hard-coded 128-program table. It loads:

```text
GET /api/rendering/options
```

The response is generated from the same `GM_PROGRAM_NAMES` table used by backend rendering validation and contains:

- supported rendering modes;
- the eight piano programs;
- all 128 General MIDI program names and MIDI-native values;
- the percussion channel number used by the API (`9`).

This makes instrument labels presentation data from the authoritative backend vocabulary rather than a parallel browser convention that can drift.

If the endpoint is unavailable, the browser falls back to Original Arrangement and does not send a non-original rendering request to an older backend.

## Request behavior

For non-original modes the existing `POST /api/queue` request receives the validated `rendering` object. Examples and full validation rules are in [API contract](api-contract.md#8-queue-commands).

Rendering is applied to every item created by that queue request. It is ephemeral and reversible. Nothing in this UI writes the asset, metadata, catalog, or current playback state directly.

## Responsive behavior

The control is collapsed to one summary row by default on the 800×480 appliance screen. Choosing a non-original mode opens the editor automatically. The expanded editor uses a denser short-landscape layout on the reference kiosk and switches override rows to a stacked layout on narrow phones.

Selectors and remove actions carry explicit labels for keyboard/screen-reader operation. The existing no-build, system-font, same-origin-only web architecture remains unchanged.
