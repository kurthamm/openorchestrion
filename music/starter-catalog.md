# Verified-Open Starter Catalog

The starter catalog is the small body of music OpenOrchestrion can ship and
stream without anyone having to take our word for it. It is deliberately not a
bulk MIDI dump: a hundred files of unknown origin are worth less than a dozen
whose terms are written down and re-checkable.

**Nothing reaches this directory without established rights.** Verified
repertoire is committed, so a user has playable, legally clean music on clone and
the appliance install has nothing to fetch — but a file earns its place by
clearing the audit, not by being convenient to add. The repository contract check
fails CI on any Git-tracked MIDI, anywhere in the repository, whose sidecar or
manifest row does not support a `verified-open` claim.

That check is repository-wide on purpose. Rejected candidates keep their
research row so nobody repeats the work, but **their bytes are never pushed** —
publishing a file whose terms we just established as non-redistributable would
be the audit's own conclusion ignored. If a rejected file needs exercising
through the importer, that handoff stays local.

Candidates arrive as raw input first: the files, plus a manifest carrying one row
of evidence per file. Only what passes is promoted. What fails stays out of the
starter set and remains perfectly usable as a personal import.

### How committed repertoire is laid out

```text
music/starter/
├── catalog.csv          the evidence: one row per file
├── maple-leaf-rag.mid
└── …
```

The manifest is the evidence, and there are deliberately **no per-file sidecars
committed beside it**. The manifest is what the installer reads, so making it the
same artifact the contract check reads means the claim CI verifies is the claim
the appliance acts on. A sidecar committed alongside would be a second copy of
the same assertion, free to drift from the one that actually takes effect.

Installing the starter catalog is therefore the ordinary manifest import:

```bash
openorchestrion-import-midi --from-csv music/starter/catalog.csv --library-root var/library
openorchestrion-reindex var/library
```

That matters more than it looks. Importing the directory *without* the manifest
would land every file as `personal` with no license, giving an appliance a
starter catalog its own stations cannot see — invisible to every `verified-open`
query. The evidence has to travel with the bytes or committing them achieves
nothing.

Because each row records a `sha256`, replacing a committed file without updating
its row is caught by CI: the row would otherwise keep vouching for bytes that are
no longer there, which is how a starter catalog ends up shipping something nobody
checked.

## The two questions

A candidate clears only when both are answered, and answering one says nothing
about the other:

1. **The composition** — is the underlying musical work out of copyright?
2. **The file** — under what terms was this particular MIDI sequencing or
   engraving released?

The second is where curation actually fails. A Joplin rag is unambiguously
public domain as a composition; a MIDI sequencing of it made in 2003 is a new
copyrightable work, and the person who made it may reserve every right. A
file being free to download says nothing at all about redistribution.

`openorchestrion.library.rights` enforces this: a `verified-open` claim missing
either half is refused at import. See
[../docs/music-sources.md](../docs/music-sources.md) for the recorded fields.

## Procedure

Everything goes through the production pipeline. There is no separate catalog
format to keep in sync — the sidecars written here are the same sidecars any
user's import produces.

### Reading the terms when you cannot reach the archive

The file-level column is filled by reading the item record, and whoever curates
often cannot reach the archive at all. There are then two ways forward and only
one of them is curation: read the page, or guess. A guessed license written into
a manifest is indistinguishable from a verified one, which is precisely the
failure this whole catalog exists to prevent.

The **Inspect curation source** workflow reads it for you. Dispatch it with the
URL of an item record; it fetches on a runner, and prints the digest, the size,
every line on the page that mentions license, copyright, attribution or
permission, and every link that leads to another item record or a MIDI file —
so a browse listing can be used to find the record before reading it. It writes nothing, opens nothing and runs with read-only
permissions — a page pulled from the open internet should not be able to reach a
branch.

What comes back is an extract, not a clearance. An item record commonly states
terms for the engraving, the score and the generated MIDI separately, and only
one of those is the file being fetched. Read the lines and decide; then dispatch
the fetch workflow with what you read.

### Fetching a candidate when you cannot reach the archive

Research and retrieval do not always happen in the same place: whoever reads a
license page may be unable to commit, and whoever commits may have no route to
the archive at all. The **Fetch curation candidate** workflow bridges that. Run
it from the Actions tab with the URL and the evidence you gathered; it fetches on
a runner, checks the file, and opens a pull request.

It refuses, in this order, before anything reaches a branch:

1. a **source host** the project has not agreed to work through;
2. a file whose **digest** is not the one the research was about;
3. anything that is **not readable MIDI with actual notes** — archives serve
   error pages with `.mid` names when a link rots;
4. a **claim its evidence cannot support**.

Supply `expected_sha256` whenever the digest was recorded. Without it the file is
still staged, but the pull request says the digest was *observed* rather than
verified — "I read this file's terms" and "I read some file's terms and this is a
file" are different claims and must not look alike in review.

The workflow is manual-dispatch only, it opens a pull request rather than pushing,
and it runs the repository contract check before doing so. A person still decides
whether the music ships.

### A curated set: one row of evidence per file

A starter catalog is not one rights claim applied to a folder. Every file has a
different source, a different license and a different composer, so evidence
applied per directory is not evidence at all — it is a guess averaged over a
folder. Fill in [starter-catalog-template.csv](starter-catalog-template.csv),
one row per candidate, and import the set in one command:

```bash
openorchestrion-import-midi --from-csv candidates.csv --library-root var/library
```

Relative `path` values resolve alongside the manifest, so the CSV travels with
the files it describes. Each row is audited on its own: a row whose evidence
does not hold up is reported with its line number and skipped, while the rest of
the set still lands. Re-running after a fix is safe — content addressing means an
already-imported file resolves to the same asset rather than a duplicate.

The optional `sha256` column is what makes researched evidence transferable.
Whoever read the license and whatever machine imports the bytes are usually not
the same person; without the digest, nothing ties a claim to any particular
sequence of bytes. A file that does not match its researched digest is refused as
a **rights** failure rather than a checksum nicety, because different bytes may
be a different arrangement under different terms.

A row may also record `rights_status: personal` — curation includes deciding
that something is *not* redistributable. The research is still stored, so nobody
repeats it, and the file simply does not join the starter set.

Then curate the descriptive metadata and index, as below.

```bash
# 1. Import with the evidence attached. Refused unless it holds up.
openorchestrion-import-midi ~/downloads/maple-leaf-rag.mid \
  --library-root var/library \
  --rights-status verified-open \
  --source-label "<archive name>" \
  --source-reference "<url of the item record>" \
  --license <established id> \
  --license-url "<url where the terms were read>" \
  --composition-rights public-domain \
  --composition-rights-basis "Composer died 1917; published 1899" \
  --redistribution permitted \
  --verified-by "<who checked>"

# 2. Curate the descriptive metadata through the writer.
openorchestrion-tag <asset-id> \
  --library-root var/library \
  --title "Maple Leaf Rag" \
  --composer "Scott Joplin" \
  --year-composed 1899 \
  --genres ragtime --moods upbeat --themes parlor \
  --performance-type SOLO_PIANO

# 3. Index it.
openorchestrion-reindex var/library
```

If research arrives after the import — the usual case, since the file is often
in hand before its terms are — use `openorchestrion-rights` rather than
re-importing, which never overwrites a stored rights record:

```bash
openorchestrion-rights <asset-id> \
  --library-root var/library \
  --rights-status verified-open \
  --source-reference "<url of the item record>" \
  --license CC0-1.0 \
  --composition-rights public-domain \
  --composition-rights-basis "Composer died 1917; published 1899" \
  --redistribution permitted \
  --verified-by "<who checked>"
```

That writes the sidecar and reconciles the catalog in one step. Only the fields
you pass are changed, and the claim is refused unless the merged result supports
it, so an incomplete revision fails rather than producing a claim that outruns
its evidence.

## Candidate compositions

The composition-level column below is research that can be done without touching
any archive, and it is the half that rarely changes. **Every file-level column
is deliberately empty**: it can only be filled by visiting the source, reading
the actual terms of the actual file, and recording where they were read.

A row here is a candidate, not a clearance. Nothing in this table may be
imported as `verified-open` until its file-level terms are established, and the
audit will refuse it if anyone tries.

### Solo piano — expressive

| Composition | Composer | Died | Composed / published | Source candidate | File license |
| --- | --- | --- | --- | --- | --- |
| Gymnopédie No. 1 | Erik Satie | 1925 | 1888 | Mutopia | _unestablished_ |
| Gnossienne No. 1 | Erik Satie | 1925 | composed 1890, published 1893 | Mutopia | _unestablished_ |
| Clair de lune (Suite bergamasque) | Claude Debussy | 1918 | 1905 | Mutopia | _unestablished_ |
| Rêverie | Claude Debussy | 1918 | composed 1890 | Mutopia | _unestablished_ |
| Nocturne in E♭, Op. 9 No. 2 | Frédéric Chopin | 1849 | 1832 | Mutopia | _unestablished_ |
| Prelude in D♭, Op. 28 No. 15 | Frédéric Chopin | 1849 | 1839 | Mutopia | _unestablished_ |
| Träumerei (Kinderszenen) | Robert Schumann | 1856 | 1838 | Mutopia | _unestablished_ |
| Für Elise | Ludwig van Beethoven | 1827 | composed 1810, published 1867 | Mutopia | _unestablished_ |

### Ragtime

| Composition | Composer | Died | Composed / published | Source candidate | File license |
| --- | --- | --- | --- | --- | --- |
| **Wall Street Rag** | Scott Joplin | 1917 | 1909 | **Wikimedia Commons** | **CC0-1.0 — cleared** |
| Maple Leaf Rag | Scott Joplin | 1917 | 1899 | Mutopia | _unestablished_ |
| The Entertainer | Scott Joplin | 1917 | 1902 | Mutopia | _unestablished_ |
| Pine Apple Rag | Scott Joplin | 1917 | 1908 | Mutopia | _unestablished_ |
| Solace | Scott Joplin | 1917 | 1909 | Mutopia | _unestablished_ |

### Classical / baroque

| Composition | Composer | Died | Composed / published | Source candidate | File license |
| --- | --- | --- | --- | --- | --- |
| Prelude in C, BWV 846 | J. S. Bach | 1750 | composed 1722 | Mutopia | _unestablished_ |
| Invention No. 1, BWV 772 | J. S. Bach | 1750 | composed 1723 | Mutopia | _unestablished_ |
| Air on the G String (BWV 1068) | J. S. Bach | 1750 | composed c. 1730 | Mutopia | _unestablished_ |
| Canon in D | Johann Pachelbel | 1706 | composed c. 1680, published 1919 | Mutopia | _unestablished_ |

### Two-piano and duet

The project's dueling-piano work needs genuine multi-performer repertoire rather
than a solo part split in half. These are written for two players.

| Composition | Composer | Died | Composed / published | Forces | File license |
| --- | --- | --- | --- | --- | --- |
| Sonata for Two Pianos in D, K. 448 | W. A. Mozart | 1791 | composed 1781 | Two pianos | _unestablished_ |
| Fantasia in F minor, D. 940 | Franz Schubert | 1828 | 1829 | Piano four hands | _unestablished_ |
| Slavonic Dances, Op. 46 | Antonín Dvořák | 1904 | 1878 | Piano four hands | _unestablished_ |
| Hungarian Dances (Nos. 1, 5) | Johannes Brahms | 1897 | 1869 | Piano four hands | _unestablished_ |

### Seasonal

Carols are the sharpest trap in this whole exercise, because the tune and the
arrangement are almost never the same age. The compositions below are old; the
*harmonization or arrangement* in any particular file may be recent and fully in
copyright.

| Composition | Composer | Died | Composed / published | Note | File license |
| --- | --- | --- | --- | --- | --- |
| Silent Night | Franz Xaver Gruber | 1863 | 1818 | Melody only; check the arrangement | _unestablished_ |
| O Holy Night | Adolphe Adam | 1856 | 1847 | Check the English translation used | _unestablished_ |
| Joy to the World | Lowell Mason | 1872 | 1848 | — | _unestablished_ |
| Hark! The Herald Angels Sing | Felix Mendelssohn | 1847 | 1840 | — | _unestablished_ |
| God Rest Ye Merry, Gentlemen | Traditional | — | pre-1800 | Traditional English carol | _unestablished_ |
| Deck the Halls | Traditional | — | 1862 (English text) | Welsh air, older | _unestablished_ |

**Excluded deliberately:** *Carol of the Bells* is the instructive counterexample.
Leontovych's *Shchedryk* is old enough, but the arrangement most people mean is
Wilhousky's from 1936 and is not ours to redistribute. It belongs in a Personal
Library import, not in the starter set.

## Determining the composition

Two independent tests, and the appliance operator's jurisdiction decides which
governs:

- **Life + 70** (EU, UK, and much of the world): the composer died more than 70
  years ago. Every composer above except Satie (1925) and Debussy (1918) clears
  this by a wide margin, and both of those cleared it years ago as well.
- **US publication cutoff**: works published before 1931 are in the public
  domain in the United States. Every publication date above precedes it.

Record whichever applies as `composition_rights_basis` in the words that make it
checkable — "composer died 1917; published 1899" — rather than the bare phrase
"public domain", which tells a later reader nothing they can verify.

Posthumous publication needs a second look rather than a reflex: several works
above were first printed after their composer died, which is harmless when that
printing is itself long past the cutoff, but a manuscript first published in
living memory can carry a fresh term in some jurisdictions. Where the two tests
disagree, or where first publication is recent, treat the composition as
unestablished and leave the piece out rather than pick the favourable answer.

## Sources still to be evaluated

These are archives worth working through, not blanket clearances. Each item
inside them must still be checked individually.

- **Mutopia Project** — engravings typeset from public-domain scores, with
  generated MIDI. Per-item terms vary between public domain, CC0, and CC-BY-SA,
  which is precisely why the license belongs on the item and not on the archive.
- **Wikimedia Commons** — per-file license templates, often with attribution or
  share-alike obligations that must be captured as `attribution` text.
- **MAESTRO** — expressive Disklavier performance captures, musically the most
  attractive option this project has, because the MIDI carries real performance
  timing, velocity and pedalling rather than quantized note entry. Its dataset
  is published under **CC-BY-NC-SA-4.0**, and the non-commercial term puts it
  outside the redistributable starter set no matter how good the performances
  are. It remains perfectly usable as a **Personal Library** import on an
  operator's own appliance. The audit recognizes this license id specifically,
  so a curator who reaches for it is told the answer is settled rather than
  merely unfamiliar.

**Not source-worthy for the starter set:** BitMidi, VGMusic and similar archives.
Free download is not a grant, and the characteristic "free for personal use"
string is refused by the audit for exactly that reason.

## Status

**One piece has cleared: Scott Joplin's *Wall Street Rag* (1909)**, from Wikimedia
Commons under CC0-1.0, now committed in `music/starter/` with its evidence in
`catalog.csv`. It is the first third-party repertoire this project has been able
to assert redistribution rights over, and it proves the pipeline end to end:
audited, imported under its own evidence, tagged, indexed, and picked up by a
station query.

Composition-level research for the remaining candidates is complete and needs
review. Their file-level terms are still outstanding — no other candidate has had
its actual MIDI file located, fetched, or its license read — so nothing else here
is yet importable as `verified-open`.

The generated conformance suite in `openorchestrion.testing.midi_fixtures` remains
the project's own content under its own license, and is separate from this
catalog.
