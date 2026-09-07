# Casio WK-220: unattended playback setup

## Disable Auto Power Off at startup

Before unattended playback or a loaded endurance run:

1. Turn the keyboard off.
2. Hold **TONE** while pressing **POWER** to turn it on.
3. Release TONE after startup.

Use this startup sequence each time unattended operation is required. Casio documents this physical-button procedure, not a persistent setting in the OpenOrchestrion website. Do not present an application checkbox as if it changed the keyboard's power management.

The [WK-220 owner's manual, printed page E-10](https://support.casio.com/pdf/008/Web_CTK4200_WK220_E_1A.pdf#page=12) specifies automatic shutdown after approximately six minutes without operation on batteries, or thirty minutes with the AC adapter. It does not establish that incoming MIDI traffic reliably resets that timer. Do not substitute undocumented MIDI keepalive messages for the documented startup procedure.

Power cycling disconnects USB MIDI and interrupts physical playback. Preserve the server queue, allow hotplug discovery to recover, then restart an interrupted acceptance run from the beginning. A connected MIDI endpoint does not prove that Auto Power Off has been disabled; record operator confirmation separately.

This is manufacturer-documented setup guidance. It is not a new acoustic or hardware-conformance result and does not change the deferred CT-X700 work.
