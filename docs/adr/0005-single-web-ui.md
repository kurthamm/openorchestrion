# ADR-0005: One responsive web application for kiosk and remote control

- **Status:** Accepted
- **Decision:** The attached touchscreen, phone/PWA, tablet, and desktop browser use the same responsive web application and server-side state.

## Context

A custom Pi-native GUI would duplicate controls, state management, and maintenance while the system already needs a household web interface.

## Consequences

- Chromium kiosk mode can make the Pi display feel appliance-like.
- A headless build uses identical server software.
- All clients synchronize through the same API/WebSocket state.
- Administrative depth can vary by route/viewport without creating a second front-end product.
- Closing a client does not stop server-side playback.
