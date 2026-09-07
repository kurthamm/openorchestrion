# Listening room redesign

## Purpose and current experience

The September 2026 redesign replaces the prompt-first interface with a music-first listening room. It addresses the previous empty landing page, mixed filter chips, first-100-results limit, missing favorites destination, unexplained MIDI arrangements and forced setup redirects.

| Destination | What the listener can do |
| --- | --- |
| Discover | Start with actual library collections and a composer selection. Counts come from the admitted catalog; artwork is decorative, not invented album artwork. |
| Music library | Search words across title, composer, artist and original filename; combine style, mood, era, arrangement, composer and source; sort and page through the complete result set. |
| Favorites | Save or remove performances and search/filter the saved collection. Favorites remain in durable sidecar metadata. |
| Play queue | Append music without interrupting playback, reorder, remove, start a session, or confirm an atomic stop-and-clear. |
| Recently played | See readable titles and last-played times. Archived or temporarily unavailable entries are identified explicitly. |
| Playback & devices | See MIDI output readiness, set master volume, and choose automatic, original, piano-only or explicit program overrides for new queue items. |

The player remains available while browsing. Its buttons and volume input keep their DOM identity as position updates arrive. On phones, navigation sits above the compact player; settings remain reachable from the top bar. Opening a performance reveals details in a keyboard-accessible native dialog, with Escape and a close button. Search state is encoded in the URL so links and browser Back/Forward retain filters and pagination.

No connected instrument is required to browse, save favorites, inspect metadata, or prepare a queue. Starting music requires a live connection and a ready output. Sound comes from the MIDI instrument, not browser speakers. Disconnection produces a quiet status notice and never forces a setup page.

## MIDI information and its limits

The performance panel reads the existing deterministic catalog analysis:

- duration, tracks, note count and active MIDI channels;
- every distinct encoded instrument/channel/program/bank combination, including changes within a channel;
- General MIDI names and program numbers, bank MSB/LSB, percussion channels;
- sustain and pitch bend, velocity range, peak simultaneous notes and pitch range;
- the catalog's arrangement label and General MIDI structural assessment;
- source collection/reference, original filename, composer, artist/context, era, rights, license and attribution.

Channel and program numbers shown to listeners are **1–16 and 1–128**. Rendering API overrides retain their existing zero-based encoding. A file with no program changes is described explicitly; no instrument is invented. Multiple tracks are not automatically described as multiple instruments. Existing descriptive arrangement labels may disagree with the encoded programs, so both are shown independently.

The chosen sound policy applies when items are added, not retroactively to an existing queue. Encoded GM names are not promises about the actual sound: device profiles, banks, drum kits, defaults and rendering overrides affect playback. SysEx remains blocked by the hardware playback path. This release does not change the admitted library, archived files, quality rules or program-preservation fixes, and it does not claim human listening validation.

## AI is intentionally deferred

The current application does not mount a chat box, assistant navigation item, AI teaser or setup checklist for a provider. Startup, search, discovery and playback make no Concierge requests. The existing backend Concierge/intent/station APIs remain compatible for existing clients.

Future AI should be a separate optional route or panel registered beside the current routes, with an independent module and explicit enablement. It should create a **reviewable selection or queue proposal** through the API seam, preserve the listener's filters and queue, and reuse the ordinary queue controls. It must not own playback timing, issue raw MIDI, replace a running session without the established confirmation, or become a dependency of browsing. No provider credentials or future AI configuration UI are added here. The deterministic automatic-voicing setting is distinct from AI.

## Implementation and contracts

- `web/index.html` and `web/app.css`: responsive shell, typography, artwork, navigation, dialogs and persistent player. Local fonts and CSS artwork keep the appliance self-contained; no remote assets, analytics or packages are loaded by the page.
- `web/js/app.js`: route/view coordination and isolated updates for the catalog, device state, queue and player. Stale search requests are aborted and version-checked. Favorite requests have per-asset pending guards; queue writes are serialized; transport command IDs reconcile socket confirmations after lost REST replies.
- `web/js/api.js`: the existing transport seam plus browse, facets, performance and clear-queue calls. The existing rendering controls and WebSocket/position modules are reused.
- `library/browse.py`: parameterized, read-only queries over admitted catalog rows. Every search word must match somewhere in title/composer/artist/filename; case and diacritics are normalized. `%` is literal, not a wildcard. Counts and pages share a SQLite read snapshot and all sorts have an asset-ID tiebreaker.
- `api/listening_models.py`: strict, path-free response models. Existing `/library/search` and `/library/assets/{id}` responses stay compatible.
- `playback/engine.py`: `clear_queue` interrupts playback and clears the queue under the same lock, with idempotent command replay protection. A retried old clear cannot delete a later session.
- Static assets revalidate, and the entry stylesheet/module and changed API import have release identifiers to avoid mixing a new shell with old cached code.

### New API surface

All paths below have the `/api` prefix; `/openapi.json` is authoritative.

| Method/path | Contract |
| --- | --- |
| `GET /library/browse` | `text` (up to 200 characters), exact `genre`, `mood`, `era`, `arrangement`, `composer`, `source`, `favorite` boolean; `sort=title/composer/duration/newest`; nonnegative `offset`, `limit=1..100` (default 40). Returns `items`, full `total`, `offset`, `limit`, `has_more`. |
| `GET /library/browse/facets` | All available genre, mood, era, arrangement, composer and source values/counts, plus total and favorite counts. Counts describe the whole library, not the currently filtered subset. |
| `GET /library/assets/{id}/performance` | Provenance and deterministic MIDI facts, grouped encoded instruments and channels. Unknown/unadmitted assets return 404. Does not expose server filesystem paths. |
| `POST /queue/clear` | Optional UUID `command_id` in a `TransportCommand` body; returns authoritative `QueueState`. Stops an active session and removes all items atomically. The ordinary queue replacement endpoint still rejects empty selections. |

## Verification and operation

Development used a separate Git worktree and a **full copied catalog and asset directory**, with a temporary history database and injected `VirtualMidiOutput`. Browser tests never sent MIDI to hardware or changed production favorites. The preview server is temporary and is stopped after release.

Validation covers cross-field/diacritic search, filter intersections, stable pages, literal wildcard characters, source/arrangement filters, path-free program details, invalid query bounds, atomic clear during playback, and old-command replay after a new queue. Existing setup-redirect tests were updated to the intentional no-redirect experience; existing position, socket, API, metadata, admission and playback tests remain in place.

The browser verification checklist includes desktop and 390/320-pixel phone layouts, horizontal overflow and navigation/player overlap, multiword search, combined arrangement filters, pagination, favorites, details, virtual play/pause, queue clear confirmation, volume/settings, and disconnected production browsing. Physical sound quality remains unverified because no keyboard is connected.

For deployment, build an isolated wheel, validate it against a temporary virtual server, retain the previous wheel, check that production playback is idle, install with `--no-deps`, and restart the application and discovery services. Verify health, admitted count, browse/detail responses, static assets, existing station selection and appliance smoke checks. A verification failure restores the previous wheel. No catalog rebuild or MIDI migration is required.

### Verified release — 7 September 2026

- Python suite: **660 passed**; existing dependency deprecation warnings only.
- Ruff correctness checks and repository/schema/generated-MIDI contracts passed.
- Node module syntax and browser favorite regression checks passed.
- Installed wheel passed a separate virtual-server smoke test, paginated browse, typed instrument details, static cache policy and clear-queue checks.
- Browser checks covered desktop, 1024-pixel tablet, 390-pixel phone and 320-pixel narrow phone layouts. The mobile navigation overlap found during testing was corrected; tested pages have no horizontal document overflow.
- Live deployment verified **20,549 admitted performances**, **136 Beethoven sonata search results**, existing classical station selection, healthy HTTP service, and discovery restart. The only readiness limitation is the already-disconnected MIDI output.
- Release wheel SHA-256: `94e08cc804dcd5e2efb85f4fb294670d9476c482ba25d214ec5125e7cd328bca`.
- Previous wheel retained on the Pi at `/tmp/openorchestrion-curation-deploy/new/openorchestrion-0.1.0.dev0-py3-none-any.whl`; SHA-256 `425979ce78b4325b523d6ff58a336b75aaabb12071264c84a44c92fe30d081e7`.
- No library migration, admission change, production favorite mutation, hardware test, or AI-provider activation occurred during this release.
