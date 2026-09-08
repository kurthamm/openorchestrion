# MIDI Source Strategy

OpenOrchestrion needs two different concepts: **free to download** and **safe to redistribute**. They are not the same thing.

## Strong open-library candidates

### Mutopia Project

Useful for classical, piano, ragtime, chamber and some orchestral material. Individual works identify their public-domain or Creative Commons status. This is a strong candidate for a verified/open starter library.

### Wikimedia Commons

Accepts public-domain or freely licensed media. Individual file terms still need to be retained, including attribution/share-alike requirements where applicable.

### MAESTRO

A large expressive piano-performance dataset captured from Yamaha Disklavier instruments. Particularly attractive because the MIDI includes real performance timing, velocity and pedals. The MIDI-only dataset is very small relative to its roughly 200 hours of music. Dataset licensing must be respected; it should not simply be copied into the repo without reviewing redistribution terms.

## Free-download sources with rights caveats

Sites such as BitMidi and VGMusic can contain huge catalogs, including pop, film, game and other modern music. A file being downloadable without charge does **not** make the composition or arrangement public domain.

OpenOrchestrion may support these files as **Personal Library** imports where appropriate, but the public repository should not redistribute them without clear rights.

## Two-piano material

The project should actively curate or index legally usable:

- true two-piano works;
- piano four-hands material whose parts can be separated;
- public-domain two-piano arrangements;
- purpose-built OpenOrchestrion dueling-piano arrangements.

A useful proof-of-concept target is Mozart's Sonata for Two Pianos in D major, K.448, using a MIDI source whose redistribution terms are compatible with the chosen use.

## General MIDI arrangements

GM/GM1 files are especially valuable because they can carry standardized instrument assignments and percussion conventions that a compatible hardware engine can interpret directly.

The importer should record whether a file appears GM-compatible and which programs/channels it requests.

## Library policy

Every indexed or bundled file tracks the following in its sidecar `provenance`
block. These are no longer aspirational: `openorchestrion.library.rights` holds
the model, and a `verified-open` claim that is not supported by them is refused
at import rather than stored.

| Field | What it records |
| --- | --- |
| `source_reference` | URL or citation, so the claim can be re-checked |
| `source_label` | Human-readable archive name |
| `composition_rights` | Rights in the underlying musical work |
| `composition_rights_basis` | Why the composition is clear, e.g. "composer died 1917" |
| `license` | License of this MIDI file/arrangement, an established id |
| `license_url` | Where those terms were read |
| `attribution` | Credit text the license obliges us to display |
| `redistribution` | `permitted`, `permitted-with-attribution`, `prohibited`, `unknown` |
| `rights_status` | `verified-open`, `personal`, `unknown` |
| `verified_at` / `verified_by` | When the terms were established, and by whom |
| `imported_at` | When the bytes arrived; not editable afterwards |

The two rights questions stay separate on purpose. A public-domain composition
sequenced by a named person in 2003 produces a new copyrightable work, and that
person may reserve every right in it. Clearing the composition says nothing
about the file.

An unrecognized license is treated as **unestablished**, not as permissive.
Adding one to the table in `openorchestrion.library.rights` is a deliberate edit
that records the review, rather than something a curator can assert in passing.
Licenses known to be incompatible with a redistributable set — anything
non-commercial or no-derivatives, including MAESTRO's `CC-BY-NC-SA-4.0` — are
named explicitly so the audit reports a settled answer rather than an unfamiliar
one. Such material is still fine as a Personal Library import.

`redistribution` is deliberately coarse: it distinguishes "credit required" from
"no credit required" and nothing more. It is **not** a distribution-compliance
engine, and `attribution_required()` should never be presented as one. A license
can oblige far more than a credit line — ShareAlike terms on a derived work, for
one. The stored `license` and `license_url` remain the source of truth for
license-specific obligations.

The public project should favor a smaller, high-quality, legally clean starter catalog over an enormous mystery archive. See [../music/starter-catalog.md](../music/starter-catalog.md) for the curation worklist and procedure.

## Bulk acquisition scripts

`tools/acquire/` holds the scripts used to build the reference appliance's
library in September 2026. Each writes a staging directory containing the MIDI
files, an importer manifest (`catalog.csv`, one rights row per file) and a
`tags.csv` for `openorchestrion-tag --from-csv`:

| Script | Source | Rights recorded |
| --- | --- | --- |
| `mutopia_crawl.py` | Mutopia Project website directory index + per-piece RDF | `verified-open` where the licence is established and the composer died before 1956; otherwise `personal` |
| `maestro_manifest.py` | MAESTRO v3 MIDI zip + CSV | `personal` (CC BY-NC-SA 4.0) |
| `commons_crawl.py` | Wikimedia Commons `Category:MIDI files` | `personal`, per-file licence recorded |
| `bitmidi_crawl.py` | BitMidi API, ordered by plays | `personal`, licence unknown |
| `curate_tags.py` | catalog analysis export | rebuilds era, genres, moods, themes, instrumentation, energy, familiarity |
| `curate_bitmidi.py` | BitMidi names and play counts | popular-music genres and themes |

They are personal-library tooling, not part of the package, and they respect the
rate limits of each archive (Commons refuses bursts with HTTP 429).


## Verified automatic source registry — 2026-09-07

Repository history documented Commons HTTP 429 bursts and an earlier manual-fetch
fallback. It did not name a complete list of inaccessible archives. The checks below
were run from the Raspberry Pi, including actual MIDI downloads where enabled.
[Probe evidence](evidence/acquisition/midi-downloads.json) and
[the automatic importer runbook](automatic-acquisition.md) are checked in.

| Source | Current automatic use | Access evidence and scope |
| --- | --- | --- |
| [Saarland Music Data v2](https://www.audiolabs-erlangen.de/resources/MIR/SMD/midi) | Enabled | Actual MIDI verified. 50 listed Disklavier piano performances. Version 2 restores sustain/soft pedal controls lost in v1. CC BY-NC-SA 3.0; retain attribution. Fixed research collection, not a daily release feed. |
| [Classical Archives: Pierre R. Schwob free collection](https://www.classicalarchives.com/prs/free.html) | Enabled | Actual MIDI verified. Only the expressly free `/prs/midi_free/` collection; no subscription catalog. Publisher credit retained. |
| [VGMusic](https://www.vgmusic.com/music/) | Enabled | Actual piano-arrangement MIDI verified. Reviewed music directories including piano arrangements; every file still requires v2 structural evidence. |
| [Mutopia](https://www.mutopiaproject.org/latestadditions.rss) | Enabled | Actual per-piece MIDI verified. RSS is dated 2019: useful for missing backcatalog, not evidence of recent publication. No bundled ZIP extraction or automatic per-work rights certification in this adapter. |
| [MIDKAR](https://midkar.com/Blues/Blues_MIDIs.html) | Enabled | Actual MIDI verified in Blues and Pop/Rock paths. MIDI/KAR only, no member areas, software or SoundFonts. Backing-track labels are a negative completeness signal, never publisher proof of a full arrangement. |
| [BitMidi](https://bitmidi.com/robots.txt) | Disabled | API returns HTTP 200, but MIDI downloads use `/uploads/`, disallowed by the current robots policy. Homepage/API availability does not establish permission to crawl downloads. Existing library files remain available. |
| [Wikimedia Commons](https://commons.wikimedia.org/wiki/Category:MIDI_files) | Disabled | API responds but tested route is disallowed by the client's robots check; old crawler also encountered HTTP 429. Needs an approved API access route before unattended use. |
| [Piano MIDI](https://www.piano-midi.de/) | Disabled | TLS certificate verification failed on the Pi. Verification is not disabled to force access. |
| [Kunst der Fuge](https://www.kunstderfuge.com/info.htm) | Disabled | Website reachable, but subscription/daily free-download limits are unsuitable for this unattended collector. |
| [MAESTRO](https://magenta.tensorflow.org/datasets/maestro) | Existing library | Already represented by 1,276 admitted publisher-verified performances. Versioned dataset, no separate daily adapter. |
| [e-Competition](https://www.ecompetition.org/about/about-e-competition) | Research candidate | Official page reachable and describes Disklavier recordings; a current direct MIDI route remains unverified. Check overlap with MAESTRO before building an adapter. |
| IMSLP / Ichigo | Research candidates | Guessed category paths returned 404; that is not evidence the whole sites are inaccessible. Work-specific download routes and metadata remain to be reviewed. |

New sources should be found through primary publisher/arranger sites and official
performance datasets, then checked in this order: current listing, an actual MIDI
file, usage/access policy, source metadata, representative arrangement quality, and
cross-library duplicate overlap. Large audio-transcribed datasets do not automatically
meet the recorded-performance standard. More files or more channels alone do not
establish completeness. Do not add sources to inflate the available count.
