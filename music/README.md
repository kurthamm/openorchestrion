# Music Directory

The public repository intentionally does **not** contain a large general-purpose MIDI collection.

Only music with clearly documented redistribution rights may be committed here, and that is now a repository contract rather than an honour system: `.github/scripts/validate_repo.py` fails CI on any `.mid` or `.midi` file under this directory that is not accompanied by a `.json` sidecar whose provenance supports a `verified-open` claim. A file with no sidecar, a sidecar marked `personal`, and a `verified-open` claim with nothing behind it are all rejected.

Personal or commercially licensed MIDI belongs in the user's local library and is excluded from source control. The importer brings it onto the appliance without it ever entering Git.

## The starter catalog

The curated starter repertoire is **assembled on the appliance**, not committed here. What lives in this repository is the evidence and the procedure: which compositions are candidates, what has to be established about each file before it can be used, and the commands that record it.

See [starter-catalog.md](starter-catalog.md) for the worklist, the curation procedure, and the sources still to be evaluated.

## Why the file matters as much as the composition

A public-domain composition and a redistributable MIDI file are different questions. A Joplin rag is unambiguously out of copyright; a MIDI sequencing of it made in 2003 is a new copyrightable work whose author may reserve every right. Being free to download grants nothing.

`openorchestrion.library.rights` records both questions separately and refuses a `verified-open` claim that answers only one. See [../docs/music-sources.md](../docs/music-sources.md) for the full field list and [../docs/midi-ingestion.md](../docs/midi-ingestion.md) for how evidence is supplied at import.
