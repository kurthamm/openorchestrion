# UX and Control Surfaces

## Product intent

OpenOrchestrion should feel like a household music appliance, not a DAW, Linux workstation, or MIDI utility. A person should be able to walk up to the system, ask for music, and hear it without understanding MIDI channels, sound banks, routing, or library internals.

The project uses **one responsive web application** for every control surface. The attached touchscreen is a kiosk client of that application, not a separate GUI codebase.

## Primary control surfaces

### Appliance touchscreen

The reference Appliance Edition uses a 7-inch touchscreen. Its job is immediate listening, not deep administration.

Recommended home surface:

```text
┌──────────────────────────────────────────┐
│              OpenOrchestrion             │
│                                          │
│  What do you want to hear?               │
│  ┌────────────────────────────────────┐  │
│  │ Popular Christmas music at dinner │  │
│  └────────────────────────────────────┘  │
│                                          │
│            ▶ Make it happen              │
│                                          │
│  Classical   Ragtime   Dinner   Xmas     │
│             🎲 Surprise Me               │
│                                          │
│  Now Playing                             │
│  Maple Leaf Rag · Scott Joplin           │
│      ◀          ❚❚          ▶             │
└──────────────────────────────────────────┘
```

The local UI should prioritize:

- AI Music Concierge prompt
- Play Something / Surprise Me
- station, theme, and genre shortcuts
- Favorites
- Now Playing
- queue
- play, pause, stop, and skip
- simple device/playback health

### Household browser / PWA

Phones, tablets, and computers use the same application over the home network, ideally through a friendly local address such as `openorchestrion.local`.

The remote experience includes everything on the kiosk plus richer browsing and configuration. PWA installation should allow an OpenOrchestrion icon to launch the application without ordinary browser chrome.

### Administration mode

Advanced administration belongs primarily on a larger browser surface:

- import MIDI
- edit metadata and rights/provenance
- manage stations and playlists
- configure hardware profiles
- route channels/tracks to devices
- perform two-device latency calibration
- configure AI provider(s)
- review backup state
- inspect logs and diagnostics

This is a depth-of-interface distinction, not a separate application.

## AI-first interaction

Natural language is a first-class entry point. Examples:

- “Play dinner music for two hours.”
- “Popular Christmas music.”
- “Relaxing classical piano, nothing dramatic.”
- “More upbeat.”
- “More recognizable.”
- “Add some Christmas music.”
- “More piano.”
- “Give me dueling pianos for the next hour.”

The UI should show a concise interpretation before or as playback begins, for example:

> Upbeat, recognizable Christmas dinner music with a piano-forward mix.

The user should be able to refine the current request conversationally rather than repeatedly rebuilding filters from scratch.

## Voice input

Speech-to-text is a desirable optional front end to the same Music Concierge prompt. Voice capture does not change the AI or playback architecture:

```text
speech → text → PlaybackIntent → deterministic selector/router
```

No voice implementation should be required for the initial MVP.

## Browse model

Manual browsing remains important when AI is unavailable or the user wants explicit control.

Browse dimensions include:

- title
- composer / artist
- genre
- era
- mood
- theme
- performance type
- instrumentation
- favorites
- recently added
- recently played
- most played
- rarely played / not heard recently

## Now Playing

Now Playing should expose enough information to make the system understandable without becoming technical clutter:

- title
- composer/artist
- performance type
- elapsed / remaining time
- station or request that selected the item
- play/pause/skip/stop
- queue access
- optional active-device summary

Advanced routing/channel details should be available through an expandable diagnostics surface, not shown by default.

## Queue behavior

The queue should support:

- reorder
- remove
- skip
- append
- replace
- AI refinement of future selections
- station-generated replenishment

A station may continuously extend the queue until a requested duration or stop condition is reached.

## Real-time synchronization

All connected clients should reflect the same server-owned state through WebSockets or an equivalent mechanism. A command from a phone must update the kiosk immediately; a pause from the kiosk must update the phone immediately.

The server remains authoritative. Browser closure must not stop playback.

## Optional guest request mode

A future jukebox-style mode may display a QR code that opens a limited request interface. Guests could browse/request songs without receiving administrative privileges.

Possible policies:

- requests enter a moderated queue rather than playing immediately;
- request limits per guest/session;
- only approved library material is visible;
- no device, AI-provider, backup, or system configuration access.

## Physical controls

The reference build is touchscreen-first, but optional physical controls can improve appliance feel:

- illuminated Play/Pause button
- rotary encoder for volume or navigation
- Stop/Panic button

Physical controls should call the same application command layer as the web UI rather than bypassing server state.

## Accessibility

- touch targets should be comfortable on a 7-inch kiosk;
- essential information should not depend on color alone;
- standard browser keyboard/focus behavior should be retained;
- text should remain readable at kiosk distance;
- the remote web UI should remain usable with standard browser accessibility tools.

## Design principle

The appliance screen answers:

> **What do you want to hear?**

The administration UI answers:

> **How is OpenOrchestrion making that happen?**
