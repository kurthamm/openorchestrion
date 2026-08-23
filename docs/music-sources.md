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
