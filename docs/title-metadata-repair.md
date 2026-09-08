# Title and identity repair — September 2026

The old BitMidi crawler copied upload labels into title and artist fields. It
did not decode HTML entities or legacy percent-encoded text, and its curator
sometimes promoted a game/film prefix to composer merely because the title
matched a classical keyword. Musical qualification did not validate these names.

## Shipped behavior

- Decode complete HTML entities and percent-byte runs (strict UTF-8, then legacy
  Windows-1252); normalize Unicode to NFC and whitespace. Preserve literal plus
  signs, undecodable escapes and international scripts.
- Treat BitMidi multiword filename delimiters and dotted upload prefixes as
  formatting. Preserve numeric suffixes visibly (`[1]`), meaningful numeric title
  hyphens and compound-name exceptions. Do not blanket-replace every hyphen or
  discard every number. Formatting alone is not verification of work identity.
- Keep `source_title`, `source_context`, `title_status` and `metadata_note` in
  durable descriptive metadata. A legacy upload prefix supplies context, not an
  artist/composer assertion. Explicit later user edits are not rewritten.
- Index these optional fields in the existing `asset_tags` table with reserved
  `identity_` kinds. The catalog schema remains backwards readable; browse/search
  can find both the corrected name and original upload/context. Accent-folded
  title sorting matches the existing accent-insensitive browse search.
- Show context separately from creator credits, mark unresolved identities on
  library cards, and expose evidence/original labels in performance details.
- Use the same normalizer for the acquisition worker, legacy BitMidi tooling and
  CSV text imports. The disabled BitMidi downloader is not re-enabled.

## Research and decisions

All 4,160 admitted BitMidi MIDI files were hash-verified and their embedded
track/text/copyright messages inspected. The initial BitMidi audit contained two
percent-encoded titles, one numeric-entity title, 1,828 titles with hyphens, and
one entirely numeric title. Hyphen presence alone was not treated as an error.

[152 exact-file decisions](evidence/title-repair/embedded-decisions.json) record
the original title, SHA-256 asset identity, required embedded text and the basis
of each correction. The migration verifies those bytes and text before applying
an override. The full private scan and before/after plan stay on the appliance;
MIDI bytes and bulk private metadata are not added to the public repository.

Examples:

| Original | Repaired or established identity |
| --- | --- |
| `%C9tude pour les petites supercordes` | Étude pour les petites supercordes |
| `&#12373;&#12424;&#12394;&#12425;&#12398;&#22799;` | さよならの夏 |
| `(The-Blues-Is)-The-Healer-1` | (The Blues Is) The Healer [1] |
| `060222-Tribute to Mozart` | Tribute to Mozart; Mozart music, Tubb adaptation explicitly distinguished |
| `070102 (I'll Love You Always)` | I'll Love You Always — Benjamin Robert Tubb |
| `10,000Years` | 100,000 Years, supported by the embedded work label |
| `73-06-cinema` | The Cinema Show; Genesis source context |
| `051230` | Keep 051230: the MIDI deliberately gives this title and credits Benjamin Robert Tubb |

The last example corrects the initial assumption that every numeric name is a
bad filename. A first track called Trumpet, Piano or Untitled is not a song title.
Ambiguous `1-3`, `149-MOON`, `86-05-domino` and `1-letthegoodtimesroll` lack
sufficient embedded identity evidence. Their publisher records also retain raw
upload labels: [1-3](https://bitmidi.com/1-3-mid),
[149-MOON](https://bitmidi.com/149-moon-mid),
[86-05-domino](https://bitmidi.com/86-05-domino-mid), and
[1-letthegoodtimesroll](https://bitmidi.com/1-letthegoodtimesroll-mid).
They remain searchable and playable with an unresolved label. No creator or
arrangement is guessed from a related-link recommendation or filename resemblance.

## Operating and reversing the repair

Run as the library service user, using a private, writable plan directory. A plan
contains original metadata; keep it with operator backups, not in a public PR.

```sh
openorchestrion-repair-titles --library-root /path/to/library \
  --plan /path/to/private/title-plan.json \
  --overrides docs/evidence/title-repair/embedded-decisions.json
openorchestrion-repair-titles --library-root /path/to/library \
  --plan /path/to/private/title-plan.json --apply
# Reverse the same saved plan if needed:
openorchestrion-repair-titles --library-root /path/to/library \
  --plan /path/to/private/title-plan.json --rollback
```

Stop the service for the batch publication so readers do not observe a mix of old
catalog and new sidecars. The tool holds the acquisition/backup snapshot lock,
checks the inventory, checks every planned metadata record before writing, uses
per-asset optimistic locking and atomic sidecar writes, and atomically rebuilds
the catalog. An interrupted batch can resume from the same plan. Conflicting
user edits cause a refusal instead of a silent overwrite. Reapplying after a
rollback requires a new plan because sidecar revisions have changed.

The migration changes metadata only. It preserves MIDI bytes/IDs, rights,
deterministic musical analysis, favorites, admission decisions and player data.
It is not another cull, an acoustic certification or a claim that every upload
label has been independently catalogued. Restored older backups must be repaired
again using a fresh plan. Tests cover decoding, punctuation, legacy credit
correction, search, inventory/conflict behavior, resumability and exact metadata
rollback without touching protected MIDI facts.

## Reference appliance publication — 7 September 2026

The applied plan updated **4,190 records**, including **2,230 changed titles**.
The personal library remains **5,861 performances**. All 4,160 BitMidi files were
hash-checked and scanned for embedded track names, text and copyright evidence.
There are 152 evidence-backed identity decisions and four explicitly unresolved
upload labels. The remaining source labels are not independently certified titles.
The repair moved 1,011 inferred artist prefixes into source context and changed
19 composer fields (13 unsupported prefix credits removed, six explicit credits added).

The private reversible plan is on the reference appliance at
`/var/tmp/openorchestrion-title-repair-state/plan.json`. Deployment fingerprints,
the player-state backup and integration report are under
`/var/tmp/openorchestrion-title-release/`. Preserve these with operator backups.
Neither the personal library nor those private snapshots belong in this repository.

The installed wheel SHA-256 is
`59630833056ce20320192170c341ec1821aaa83ee7462e16ed6fee253de04a5c`
(110 runtime files). An isolated non-editable wheel passed the application smoke
check before publication. The final full Pi suite passed **759 tests**; Ruff and
repository contracts passed, including the 18-file redistributable starter catalog.
Deployment verified unchanged MIDI hashes, protected metadata, favorites, admission,
queue, collections and saved player settings. Service-user write permissions and
the catalog transaction lock were checked after restoring ownership of migrated
sidecars, locks and catalog. The live browser showed corrected titles, source
context, unresolved badges, and the embedded-evidence explanation for `051230`.
The original encoded title remains searchable through the API.
