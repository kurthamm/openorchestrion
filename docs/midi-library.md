# MIDI Library

## Design goal

The library should feel like a music service, not a filesystem browser. MIDI assets remain local for playback, while metadata makes them searchable by musical intent.

## Asset model

Each performance consists of:

- the `.mid` file;
- durable sidecar metadata or equivalent exportable metadata;
- a SQLite index for fast queries and runtime state.

SQLite is treated as rebuildable. The durable library should survive a database rebuild or device replacement.

## Suggested metadata

```json
{
  "title": "Maple Leaf Rag",
  "composer": "Scott Joplin",
  "year_composed": 1899,
  "genres": ["ragtime"],
  "moods": ["energetic", "playful", "rhythmic"],
  "themes": ["ragtime", "old-time piano", "Americana"],
  "performance_type": "SOLO_PIANO",
  "familiarity": "high",
  "source": "example-source",
  "rights_status": "verified-open",
  "license": "Public Domain",
  "duration_seconds": 188,
  "quality_grade": "B"
}
```

## Deterministic MIDI analysis

The importer should derive objective facts directly from the file:

- SMF type.
- Duration.
- Tempo map.
- Time signatures.
- Track count.
- MIDI channels used.
- Program Change and Bank Select events.
- Percussion usage.
- Sustain and other controllers.
- Pitch bend and aftertouch usage.
- Note range.
- Note count and velocity distribution.
- Estimated peak simultaneous voices.
- Potential device-specific issues.

## Performance quality

Not all MIDI is equal. Suggested quality grades:

- **A:** captured human performance with expressive timing/velocity/pedal.
- **B:** carefully programmed expressive MIDI.
- **C:** accurate score-generated MIDI that may sound mechanical.
- **D:** uncertain/transcribed material requiring review.

This allows the library to prefer more musical performances without discarding usable score-derived files.

## Performance types

- `SOLO_PIANO`
- `MULTI_INSTRUMENT`
- `PIANO_DUET`
- `TWO_PIANO`
- `DUELING_PIANO`
- `DISTRIBUTED`

## Rights model

### Verified/Open

Material with explicit provenance and a known public-domain or compatible open license. Potential sources include Mutopia, Wikimedia Commons, and other sources evaluated file-by-file.

### Personal

Files imported by the user whose redistribution rights are unknown or restricted. These remain outside the public repository.

A composition being public domain does not prove that a specific modern arrangement/performance file is public domain.

## Candidate source categories

- Expressive piano-performance datasets.
- Public-domain classical MIDI.
- Public-domain ragtime.
- Chamber and orchestral MIDI.
- General MIDI arrangements.
- Purchased or personally owned MIDI collections.

## Smart stations

Stations are database queries plus weighting rules rather than fixed playlists. Examples:

- Relaxing classical, no repeat within 30 days.
- Ragtime, mostly Scott Joplin.
- Dinner music, recognizable, medium/low energy.
- Popular Christmas music.
- Orchestral Christmas.
- Cocktail jazz.
- Two-piano repertoire.
- Something not heard recently.

Rules may avoid consecutive works by the same composer, prefer 3–6 minute pieces, weight favorites, and occasionally surface rarely played works.

## Import pipeline

```text
Incoming MIDI
    │
    ▼
Structural analyzer
    │
    ├─ duration / tempo
    ├─ channels / programs
    ├─ controllers / sustain
    └─ peak polyphony estimate
    │
    ▼
Compatibility assessment
    │
    ▼
Metadata normalization
    │
    ├─ deterministic fields
    └─ optional AI enrichment
    │
    ▼
Rights/provenance review
    │
    ▼
Library index
```

## Cloud storage

MIDI files are tiny, so cloud storage is attractive for backup. The preferred model is **cloud backup + local playback**, not live streaming from a cloud drive. A Pi can synchronize or restore the library without introducing Internet availability into musical timing.
