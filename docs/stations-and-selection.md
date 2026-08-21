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

Weights should be configurable and explainable enough to debug surprising selections.

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

## Familiarity and popularity

“Popular” and “recognizable” are subjective metadata, not MIDI facts. They may come from curated metadata, user ratings, AI enrichment, or future external datasets. Their provenance should be retained.

## Selection transparency

For debugging and optional user explanation, the selector should be able to record why an item was selected, for example:

```json
{
  "track": "example-id",
  "selected_for": ["Christmas", "high familiarity", "piano-forward"],
  "score": 0.87,
  "history_adjustment": 0.12,
  "last_played_days": 74
}
```

This information is diagnostic and need not clutter the normal appliance UI.

## Failure behavior

If a request is too restrictive to produce a useful queue, the engine should relax soft preferences before violating hard exclusions. It should never invent library content that does not exist.

A useful response is:

> I found 12 matching pieces. I relaxed the “high familiarity” preference to keep the music going for two hours.

The AI may explain the relaxation, but the deterministic selector owns it.
