# Music Directory

The public repository intentionally does **not** contain a large general-purpose MIDI collection.

Only music with clearly documented redistribution rights may be committed here, and that is now a repository contract rather than an honour system: `.github/scripts/validate_repo.py` fails CI on any `.mid` or `.midi` file under this directory that is not accompanied by a `.json` sidecar whose provenance supports a `verified-open` claim. A file with no sidecar, a sidecar marked `personal`, and a `verified-open` claim with nothing behind it are all rejected.

Personal or commercially licensed MIDI belongs in the user's local library and is excluded from source control. The importer brings it onto the appliance without it ever entering Git.

## The starter catalog

Verified repertoire **is committed here**, once — and only once — its rights are established. A file reaches this directory by clearing the audit, never by being convenient to add: `.github/scripts/validate_repo.py` fails CI on any `.mid` here without a sidecar supporting a `verified-open` claim, so the gate is enforced rather than remembered.

That means a user gets playable, legally clean repertoire on clone, and the appliance install has nothing to download. It also means every future addition faces the same evidence bar, which is the point rather than the cost.

Candidates arrive as raw input first — files plus a curation manifest — and are promoted here only after the audit passes. Anything that fails stays out of the starter set; it remains fine as a personal import on someone's own appliance.

See [starter-catalog.md](starter-catalog.md) for the worklist, the curation procedure, and the sources still to be evaluated.

## The one exception: generated fixtures

The conformance suite produced by `openorchestrion.testing.midi_fixtures` is the only MIDI this project holds a `verified-open` record for. Those files are **offered under the project's MIT license**, the same terms as the repository itself — an explicit grant covering the generated output, not an inference from the generator source code's license. They contain no third-party composition, so no separate composition-level permission is involved.

They are not committed here either: the suite is generated on demand and the output directory is ignored by Git. See [../docs/test-strategy.md](../docs/test-strategy.md#rights-in-the-generated-fixtures).

## Why the file matters as much as the composition

A public-domain composition and a redistributable MIDI file are different questions. A Joplin rag is unambiguously out of copyright; a MIDI sequencing of it made in 2003 is a new copyrightable work whose author may reserve every right. Being free to download grants nothing.

`openorchestrion.library.rights` records both questions separately and refuses a `verified-open` claim that answers only one. See [../docs/music-sources.md](../docs/music-sources.md) for the full field list and [../docs/midi-ingestion.md](../docs/midi-ingestion.md) for how evidence is supplied at import.
