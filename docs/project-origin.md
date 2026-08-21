# Project Origin

OpenOrchestrion started with a simple desire: **a player piano**.

The initial idea was a Raspberry Pi in a purpose-built case with a touchscreen. The user would choose music, random play, themes, or genres such as classical and ragtime. An electronic piano with MIDI support would receive the performances.

That idea evolved through a series of architectural realizations.

## 1. The web UI became the real control surface

Rather than building a one-off Pi GUI, the attached touchscreen can simply run the same responsive web application used by phones, tablets, and computers around the house.

The Pi becomes a local server, potentially discoverable through a friendly hostname. Chromium kiosk mode makes the attached display feel like a dedicated appliance rather than a general-purpose computer.

## 2. The music library became smarter than folders

MIDI files are tiny, so storage is not the constraint. The useful problem is **selection and metadata**.

The library therefore evolved toward tags for composer, genre, era, mood, theme, familiarity, performance type, quality, source, and rights status. Smart stations can generate queues dynamically instead of requiring fixed playlists.

Examples:

- classical
- ragtime
- relaxing
- dinner music
- cocktail hour
- old-time piano
- Christmas
- Broadway/movie music
- favorites
- rarely heard music

## 3. Performance MIDI matters

A MIDI file is not just the notes. Expressive performances can contain velocity, sustain, timing nuance, and other controller information. Human-performance MIDI can sound dramatically more musical than a mechanically exported score.

The library therefore distinguishes captured/expressive performance material from score-generated MIDI.

## 4. The keyboard is not really a keyboard

Nobody in the target household needs to play the instrument.

That changed procurement completely. Weighted action, key feel, and physical key count stopped being primary criteria. The actual target is:

> a MIDI-addressable hardware sound engine with built-in audio that happens to have a keyboard attached.

This realization made inexpensive used arranger keyboards much more interesting than expensive digital pianos.

## 5. MIDI receive became a hard requirement

The system requires:

```text
Raspberry Pi → MIDI → hardware sound engine → speakers
```

A device that only sends MIDI **out** is not appropriate. Manufacturer documentation or physical validation of inbound MIDI is required.

The Casio CT-X700 emerged as a reference candidate because its documentation explicitly supports computer-to-keyboard MIDI playback and it offers General MIDI/multitimbral functionality, an AiX sound engine, many tones, and built-in speakers.

## 6. It stopped being only a player piano

The CT-X700 and similar devices can reproduce multiple MIDI instrument parts. That means one box can render piano, bass, strings, brass, woodwinds, drums, organ, synths, and more from a multichannel MIDI arrangement.

The project had become a **networked MIDI jukebox/orchestrion**, not merely an automated piano.

## 7. A second keyboard became musically useful

A second sound engine adds:

- independent synthesis/polyphony capacity;
- a different manufacturer's tone palette;
- track/channel routing;
- true two-piano repertoire;
- separated piano-duet material;
- purpose-built dueling-piano arrangements;
- future spatial/multi-room possibilities.

One Raspberry Pi remains the master clock so both local devices follow the same sequencer.

## 8. Natural language became the ideal appliance interface

Once the library has rich metadata, forcing a household user through complex filters is unnecessary. The desired experience is simply:

> “I need dinner music.”

or:

> “Play popular Christmas music.”

or:

> “Give me relaxing classical, but make it more recognizable and a little more upbeat.”

The AI Music Concierge translates that request into structured playback intent. The deterministic music engine then executes it.

## 9. The name changed

“Player Piano” became too narrow. **OpenOrchestrion** reflects both the historical lineage of automatic ensemble instruments and the modern open-source, MIDI-driven architecture.

The project can still behave like a player piano, but it can also be a jazz combo, orchestra, Christmas station, two-piano system, or networked multi-room MIDI appliance.

## Guiding question

The project can be summarized by the question that started it:

> **What would a player piano look like if it were invented today?**
