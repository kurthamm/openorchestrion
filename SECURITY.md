# Security Policy

OpenOrchestrion is intended primarily for trusted home networks, but it still exposes a network-controlled device capable of producing audio and changing local system state.

Security goals include:

- Bind management interfaces deliberately rather than exposing them unintentionally.
- Avoid Internet-facing deployment by default.
- Require authentication before any future remote/cloud-control feature.
- Store API keys and backup credentials outside source control.
- Validate uploaded/imported files.
- Never execute content embedded in MIDI metadata.
- Keep AI provider credentials isolated from the public web client.
- Validate AI output against a strict `PlaybackIntent` schema before execution.
- Keep backup credentials separate from the playback web application.
- Apply OS and dependency updates through a documented maintenance process.
- Default to local-only playback if AI/cloud services are unavailable.

Security issues should not be filed with sensitive exploit details in a public issue. Until a dedicated private reporting mechanism is configured, contact the repository owner directly through GitHub.
