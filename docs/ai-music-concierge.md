# AI Music Concierge

## Goal

A user should be able to describe the desired listening experience instead of navigating rigid menus.

Examples:

- “Play dinner music for about two hours.”
- “I want popular Christmas music.”
- “Play upbeat ragtime, mostly Joplin.”
- “Give me relaxing classical piano, nothing too dramatic.”
- “Play recognizable jazz standards for cocktails.”
- “Christmas music, but orchestral instead of solo piano.”
- “Give me dueling pianos for the next hour.”
- “A little more upbeat.”
- “More recognizable.”
- “More piano.”

The system should be able to show a concise interpretation such as:

> Upbeat, recognizable Christmas dinner music with a piano-forward mix.

## Safety boundary

The AI layer must **never directly control MIDI devices**. It returns structured intent. The deterministic OpenOrchestrion engine validates that intent, selects library material, builds the queue, and executes MIDI playback.

```text
Prompt
  │
  ▼
LLM / local model
  │
  ▼
PlaybackIntent JSON
  │
  ▼
Schema validation
  │
  ▼
Library / station engine
  │
  ▼
Queue
  │
  ▼
MIDI playback
```

This preserves a clean security and reliability boundary. An AI model cannot invent a SysEx command and send it directly to a device.

## PlaybackIntent

A first-pass intent model should support:

- `duration_minutes`
- `genres`
- `moods`
- `themes`
- `eras`
- `composers`
- `artists`
- `familiarity`
- `instrumentation`
- `performance_types`
- `tempo_preference`
- `energy`
- `include_tags`
- `exclude_tags`
- `avoid_recent_repeats`
- `repeat_window_days`
- `device_preferences`
- `routing_preferences`
- `continuation_behavior`

The AI may recommend preferences. The deterministic selector decides which real catalog items satisfy them.

## Library reality boundary

The AI must not become an imaginary music database. It may interpret “popular Christmas music,” but it cannot assert that a specific track exists unless the library service confirms it.

```text
AI: desired characteristics
Library: actual available tracks
Selector: final queue
```

If too few tracks satisfy every soft preference, the deterministic selection layer may relax soft constraints while preserving hard exclusions. The UI may explain that relaxation rather than silently fabricating content.

## Conversational refinement

The Music Concierge should retain the current session context. If the user first requests dinner music and then says “more upbeat,” the second turn modifies the existing station rather than starting from a blank slate.

Suggested session state:

```text
CurrentIntent
CurrentQueue
CurrentStation
LastUserRequest
LastInterpretation
```

A sequence such as:

```text
Play dinner music
→ more upbeat
→ more recognizable
→ add Christmas music
→ more piano
```

should converge on one refined active intent.

## Voice input

Voice is an optional input method, not a second control architecture:

```text
speech-to-text
     │
     ▼
text prompt
     │
     ▼
PlaybackIntent
```

A browser, local speech engine, or external assistant may provide transcription later. Voice input must still pass through the same schema validation and deterministic selection path.

## AI provider abstraction

OpenOrchestrion should not require a specific vendor. A provider interface can support:

- hosted LLM provider
- local model
- OpenAI-compatible endpoint
- deterministic/no-AI provider

The provider contract returns the same validated intent shape regardless of implementation.

AI provider selection must not affect the MIDI scheduling architecture.

## AI Librarian

A separate AI-assisted workflow may enrich library metadata during import. Suggested fields include genre, era, mood, theme, familiarity, dinner suitability, cocktail suitability, holiday association, and descriptive tags.

Objective MIDI facts such as channel count, duration, Program Change values, note range, and measured peak polyphony must come from deterministic analysis, not AI inference.

AI-generated metadata should retain provenance, for example:

```json
{
  "theme": "dinner",
  "source": "ai_enrichment",
  "model": "provider/model",
  "confidence": 0.83
}
```

AI suggestions should be reviewable/overridable and must never overwrite curated rights/provenance facts without explicit confirmation.

## Future: AI Arranger

A later experimental feature could manipulate arrangements, for example:

- “Make this piano only.”
- “Put the piano on Yamaha and the orchestra on Casio.”
- “Turn this into a two-keyboard arrangement.”
- “Make the two keyboards trade verses.”

This belongs after stable playback/routing because it changes musical structure rather than merely selecting music.

Any generated/modified arrangement should be saved as a new derived asset with provenance rather than silently altering the original MIDI file.

## Offline behavior

AI is optional. If unavailable, the application must continue to support:

- browsing
- search
- fixed and smart stations
- themes/genres/moods
- favorites
- random play
- queue control
- local MIDI playback

An already-built queue or active station should continue to play if the AI provider or Internet becomes unavailable.

## Testing

Use deterministic fake providers in CI to verify:

- valid prompt → valid intent
- conversational refinement
- unknown fields rejected
- hard exclusions preserved
- nonexistent catalog items are not fabricated
- provider outage fallback
- AI layer has no direct MIDI device access
