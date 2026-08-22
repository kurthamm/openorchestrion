# Smart Stations and Music Selection

## Goal

OpenOrchestrion should choose music more like a thoughtful host than a filesystem shuffle command. Stations are **dynamic queries plus weighting and sequencing rules**, not static playlists.

The AI Music Concierge may describe the desired listening experience, but the station engine makes the actual deterministic library choices.

## Selection pipeline

```text
User request / station preset
            │
            ▼
     validated PlaybackIntent
            │
            ▼
       eligibility filter
            │
            ▼
        weighted scoring
            │
            ▼
       sequencing rules
            │
            ▼
          queue
```

## Current implementation

The first deterministic selector is implemented in `openorchestrion.stations` and exposed as:

```bash
openorchestrion-station var/library/catalog.db \
  --theme dinner \
  --mood relaxed \
  --energy low \
  --duration-minutes 120 \
  --seed 42
```

For machine-readable output:

```bash
openorchestrion-station var/library/catalog.db \
  --theme Christmas \
  --familiarity high \
  --json
```

A previously validated `PlaybackIntent` can be supplied directly:

```bash
openorchestrion-station var/library/catalog.db \
  --intent-json playback-intent.json \
  --seed 42 \
  --json
```

The selector currently supports:

- genres, moods, themes, eras, instrumentation, and performance types;
- preferred composers and artists;
- familiarity and energy preferences;
- favorite and MIDI-quality weighting;
- hard include/exclude tags;
- rights-status filtering;
- maximum peak-simultaneous-note constraints;
- MIDI receive-range constraints;
- optional SysEx exclusion;
- optional GM-compatible-structure requirement;
- recent asset/composition exclusions supplied by a future history service;
- best-performance selection when multiple assets represent one composition;
- composer diversity penalties;
- abrupt energy-transition penalties;
- requested-duration/overshoot consideration;
- deterministic seeded variation;
- per-item score explanations and sequence adjustments;
- explicit soft-preference relaxation diagnostics.

The output contract is documented by `schemas/station-queue.schema.json`.

Example declarative station ideas live in `config/stations.example.yaml`.

## Matching tiers

Metadata such as genre, theme, mood, era, instrumentation, and performance type participates in three matching tiers:

1. **Exact** — all requested identity categories match.
2. **Partial** — at least one requested identity category matches.
3. **Fallback** — the asset is still eligible but does not match the requested identity metadata.

The selector exhausts stronger tiers before widening to weaker ones when additional material is needed. Widening is recorded in `relaxations` so the application can explain what happened.

Composer and artist requests are intentionally treated as **weighted preferences**, not tier gates. That distinction lets a request such as “ragtime, mostly Joplin” favor Scott Joplin strongly while still allowing another ragtime composer to appear for variety.

## Hard constraints versus soft preferences

Hard constraints are never silently relaxed. Current hard constraints include:

- explicit `exclude_tags`;
- explicit `include_tags`;
- caller-supplied rights-status restrictions;
- caller-supplied MIDI/device limits;
- explicit asset/composition exclusions;
- recent-item exclusions when `avoid_recent_repeats` is enabled.

Genres, themes, moods, familiarity, energy, composer preference, and similar listening characteristics are scored and may be widened only when necessary to build a useful queue.

## Performance choice within a composition

If several MIDI assets represent the same composition, OpenOrchestrion chooses one playable asset before sequencing the station. The choice considers match tier, preference score, quality grade, and seeded deterministic tie-breaking.

This prevents three different MIDI performances of *Maple Leaf Rag* from appearing as three separate songs in one station while still letting the library retain all three performances.

## Explainable scoring

Every queue item carries:

- `base_score`;
- final `score`;
- `selected_for` reasons;
- `score_breakdown`;
- `sequence_adjustments`;
- `match_tier`.

Example diagnostic shape:

```json
{
  "title": "Example Piece",
  "score": 31.4,
  "selected_for": ["theme match", "familiarity 5/5", "quality A"],
  "score_breakdown": {
    "theme": 14.0,
    "familiarity": 8.0,
    "quality": 5.0,
    "seeded_jitter": 0.4
  },
  "sequence_adjustments": {
    "same_composer": -14.0
  }
}
```

The normal touchscreen does not need to show this machinery, but the admin UI and tests can use it to explain surprising choices.

## Eligibility filters

A request may constrain:

- genre
- composer/artist
- era
- mood
- theme
- instrumentation
- performance type
- energy
- tempo
- familiarity
- source/rights class
- quality grade
- device compatibility
- explicit include/exclude tags

A track that cannot be safely rendered on the active hardware may be excluded or routed through an approved fallback.

Tempo preference is present in `PlaybackIntent`, but the first catalog does not yet index a useful tempo summary. The selector therefore reports that preference as a diagnostic rather than pretending to honor data it does not have.

## Weighting

After filtering, eligible tracks receive scores. Candidate signals include:

- requested genre/theme match
- requested mood/energy match
- familiarity/popularity preference
- favorite status
- quality grade
- suitability for current active devices
- time since last play
- total play count
- rarity/discovery boost
- preferred duration
- composer/artist diversity
- requested instrumentation balance

The current engine implements the metadata, favorite, quality, device-limit, duration, composer-diversity, and energy-transition portions. Play-count and rarity weighting will be added when durable play history exists.

Weights are explicit in `StationWeights` rather than buried in opaque model behavior.

## Sequencing rules

The station engine should support rules such as:

- do not repeat the same track within N days;
- avoid playing the same composer/artist consecutively;
- avoid abrupt mood/energy changes unless requested;
- prefer 3–6 minute pieces for background stations when appropriate;
- periodically introduce a rarely played work;
- prevent an overrepresented composer from dominating a long session;
- preserve explicit user queue requests ahead of generated material;
- honor requested session duration without cutting a work unnecessarily when practical.

The first selector already implements composer-repetition/representation penalties, energy-transition penalties, and requested-duration overshoot penalties. Recent-item exclusion is supported as an input contract; the durable history service still needs to produce those recent IDs.

## Example stations

### Relaxing Classical

```text
genres: classical
moods: relaxing, reflective
energy: low
avoid_recent_repeats: true
repeat_window_days: 30
quality_preference: A,B
```

### Ragtime Radio

```text
genres: ragtime
composer_weight:
  Scott Joplin: high
composer_diversity: enabled
energy: medium-high
```

### Dinner Music

```text
themes: dinner
energy: low-medium
familiarity: medium-high
instrumentation: piano, small ensemble, light orchestra
avoid_abrupt_transitions: true
```

### Popular Christmas

```text
themes: Christmas
familiarity: high
mix: solo piano + ensemble
continuation: continuous
```

### Old-Time Piano

Possible tags include ragtime, early jazz, stride, Americana, saloon/old-time piano, and turn-of-the-century material.

### Something I Haven't Heard Recently

Strongly weight `last_played` and low play count while retaining a minimum quality threshold.

### Two Pianos

Require `TWO_PIANO` or approved separable `PIANO_DUET` material and two compatible output destinations.

## Conversational refinement

A Music Concierge refinement modifies the active station model.

Example:

```text
Initial:  “Play dinner music.”
Refine:   “A little more upbeat.”
Refine:   “More recognizable.”
Refine:   “Add Christmas music.”
Refine:   “More piano.”
```

The final active intent becomes a merged set of constraints and preferences. Already queued material may remain or be regenerated according to `continuation_behavior` (`replace`, `refine`, or `append`).

## History is a core input

Every completed or substantially played track should generate a play-history event. History enables:

- no-repeat windows
- rarely played discovery
- most-played views
- “not heard recently” stations
- long-term diversity

The system should distinguish a track merely queued from one actually played.

The station selector already accepts `recent_asset_ids` and `recent_composition_ids`. The missing component is the durable history store that calculates those sets for the requested `repeat_window_days`.

## Familiarity and popularity

“Popular” and “recognizable” are subjective metadata, not MIDI facts. They may come from curated metadata, user ratings, AI enrichment, or future external datasets. Their provenance should be retained.

## Selection transparency

For debugging and optional user explanation, the selector records why each item was selected and any sequencing penalty applied. This information is diagnostic and need not clutter the normal appliance UI.

## Failure behavior

If a request is too restrictive to produce a useful queue, the engine relaxes soft preferences before violating hard exclusions. It never invents library content that does not exist.

A useful response is:

> I found 12 matching pieces. I relaxed the exact metadata match to keep the music going for two hours.

The AI may explain the relaxation, but the deterministic selector owns it.
