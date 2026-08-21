# Contributing to OpenOrchestrion

OpenOrchestrion welcomes contributions that improve reproducibility, hardware compatibility, library quality, timing, user experience, AI intent handling, and documentation.

## Especially useful contributions

- Confirmed inbound-MIDI behavior for specific keyboard models.
- Manufacturer documentation links and MIDI implementation charts.
- Tested device profiles and program/bank maps.
- Measured MIDI-to-audio latency data.
- Compatibility tests for expressive piano MIDI and GM arrangements.
- Multi-device timing tests.
- AI Music Concierge provider adapters and intent tests.
- Public-domain or clearly licensed MIDI source indexes.
- Metadata importers and enrichment tools.
- Accessibility improvements.
- Raspberry Pi installation and kiosk-mode improvements.

## Hardware claims

Please distinguish:

- **Documented compatible:** supported by manufacturer documentation.
- **Community tested:** confirmed on physical hardware by a contributor.
- **Project validated:** reproduced in the reference OpenOrchestrion build.

Do not mark a device supported simply because it has a USB connector or the word MIDI in a listing. OpenOrchestrion requires documented or physically verified **MIDI receive** from the host into the device's internal sound engine.

## Music and copyright

Do not submit copyrighted MIDI arrangements unless the repository has clear permission to redistribute them. A public-domain composition does not automatically make every modern arrangement or performance file public domain.

Every music file proposed for inclusion must include source and rights metadata.

## AI contributions

AI is an intent interpreter, not a MIDI execution engine. Provider integrations should return validated application-level intent such as genres, moods, themes, duration, familiarity, instrumentation, performance type, and routing preferences. The core application must remain functional when AI is disabled.

## Development direction

The initial implementation target is Python 3.11+ on Raspberry Pi OS / Linux. Keep device-specific logic behind capability profiles and routing abstractions rather than embedding model checks throughout the application.
