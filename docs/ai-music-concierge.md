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

The system can retain a concise interpretation such as:

> Upbeat, recognizable Christmas dinner music with a piano-forward mix.

## Current implementation

The first provider-neutral Concierge pipeline is implemented in `openorchestrion.ai`.

It has four separate responsibilities:

```text
natural language
      │
      ▼
MusicConciergeProvider
      │
      ▼
strict PlaybackIntent validation
      │
      ▼
validated PlaybackIntent
      │
      ▼
Smart Station selector
```

The AI/provider layer ends at the validated `PlaybackIntent`. It has no playback-engine, catalog-mutation, or MIDI-device handle.

### Strict structured-model adapter

`ValidatingJSONConciergeProvider` wraps a minimal `IntentBackend` interface. A future hosted model, local model, or OpenAI-compatible provider only needs to implement:

```text
generate_intent(
    prompt,
    current_intent,
    contract
) -> JSON object/string
```

The returned object must validate as `PlaybackIntent`.

Unknown fields are forbidden by the Pydantic model as well as the JSON Schema. A provider response containing invented fields such as `midi_command`, `sysex`, `play_this_url`, or any other non-contract instruction is rejected rather than ignored.

For conversational refinement, the validation boundary also verifies that existing hard `include_tags` and `exclude_tags` were not silently dropped by the model.

### Offline deterministic fallback

`DeterministicConciergeProvider` handles a deliberately small set of common household requests without Internet or a language model. It exists for:

- provider outages;
- offline operation;
- deterministic CI tests;
- basic useful control when AI is disabled.

It currently understands the project’s core examples, including dinner, Christmas, cocktail, classical, jazz, ragtime/Joplin, relaxing/upbeat, recognizable/popular, piano, orchestral, two-piano, dueling-piano, and common duration phrases.

It is not presented as a replacement for a general LLM. It is the appliance’s graceful fallback.

### Resilient service

`MusicConcierge` tries the configured primary provider first. If it raises an exception or returns invalid structured output, the request falls back to the deterministic provider. The result records:

- provider used;
- whether fallback occurred;
- primary-provider error when applicable;
- final validated intent.

Provider failure therefore does not disable ordinary local music selection.

### Conversational session

`ConciergeSession` stores the active intent between turns.

Example:

```text
Play dinner music for two hours
→ A little more upbeat
→ More recognizable
→ Add Christmas music
→ More piano
```

The final intent retains the two-hour dinner context while refining energy, familiarity, theme, and instrumentation.

## CLI

The initial CLI exposes the deterministic/offline path:

```bash
openorchestrion-concierge "Play dinner music for two hours" --json
```

A refinement can be tested against an existing intent:

```bash
openorchestrion-concierge "More upbeat" \
  --current-intent-json current-intent.json \
  --json
```

Provider-specific hosted/local adapters are intentionally separate integrations. Adding one must not change the downstream station, playback, or MIDI contracts.

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

The intent model supports:

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

There is intentionally no arbitrary track/URL/playback-command field in `PlaybackIntent`.

If too few tracks satisfy every soft preference, the deterministic selection layer may relax soft constraints while preserving hard exclusions. The UI may explain that relaxation rather than silently fabricating content.

## Conversational refinement

The Music Concierge retains current session context. A second-turn request such as “more upbeat” modifies the existing station rather than beginning from a blank intent.

Suggested higher-level session state remains:

```text
CurrentIntent
CurrentQueue
CurrentStation
LastUserRequest
LastInterpretation
```

`ConciergeSession` currently owns the intent portion. Queue/station state will be owned by the playback/application state machine rather than the model provider.

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

A browser, local speech engine, or external assistant may provide transcription later. Voice input must still pass through the same validation and deterministic selection path.

## AI provider abstraction

OpenOrchestrion does not require a specific vendor. The backend seam can support:

- hosted LLM provider;
- local model;
- OpenAI-compatible endpoint;
- other structured-output provider;
- deterministic/no-AI fallback.

The provider contract always returns the same validated intent shape. AI provider selection must not affect the MIDI scheduling architecture.

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

AI is optional. If unavailable, the application continues to support browsing, search, Smart Stations, favorites, queue control, local MIDI playback, and the deterministic Concierge fallback.

An already-built queue or active station continues to play if the AI provider or Internet becomes unavailable.

## Testing

The repository now includes tests for:

- dinner-duration interpretation;
- popular Christmas interpretation;
- relaxing classical piano interpretation;
- multi-turn conversational refinement;
- dueling-piano interpretation;
- solo-piano to orchestral refinement;
- rejection of model-hallucinated fields;
- preservation of hard exclusions during model refinement;
- primary-provider outage fallback;
- strict `PlaybackIntent` extra-field rejection.

Provider-specific adapters should use deterministic fake backends in CI and must never require live external API calls for the core regression suite.
