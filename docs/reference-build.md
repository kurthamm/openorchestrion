# Reproducible reference builds

The deployed sound engine is a **Casio WK-220** on Raspberry Pi 5.
CT-X700 remains a future target. Earlier CTK-6200 / PSR-EW300 procurement
discussions are historical alternatives, not a shopping requirement.
See [supported hardware](supported-hardware.md).

## First installation: headless

Use a Pi 5 with 4 GB RAM, suitable power supply, active cooling, microSD storage,
network connection and one documented-compatible USB MIDI keyboard with its own
power supply. Use the UI from a phone, tablet or computer. A touchscreen is optional.

The current reference uses a 32 GB card. Capacity planning includes OS updates,
backup staging and archived excluded music. A 128 GB high-endurance card is an
optional build choice, not a software minimum.

## Household appliance design and bill of materials

Use replaceable commercial modules with mains adapters outside the enclosure.
Place a ventilated headless module beside the instrument; add a separately mounted
screen for the display variant. No custom fabrication is required for first use.

| Quantity | Item | Selection and assembly requirement |
| --- | --- | --- |
| 1 | Raspberry Pi 5, 4 GB | [Manufacturer specification](https://www.raspberrypi.com/products/raspberry-pi-5/). More RAM is optional. |
| 1 | 5V/5A USB-C supply | Official 27W supply or manufacturer-compatible equivalent; keyboard powered separately. |
| 1 | Pi 5 case with cooling | [Official Pi 5 case](https://www.raspberrypi.com/products/raspberry-pi-5-case/) includes a fan. A ventilated compatible case with Active Cooler is an alternative, not an additional mandatory cooler. |
| 1 | microSD and initial reader | Raspberry Pi OS 64-bit; capacity for recovery archives and temporary update wheels. NVMe requires its own compatible mounting. |
| 1 | USB MIDI data cable | Pi USB-A to the keyboard's actual device connector; WK-220 uses USB-B. Choose length without socket tension. |
| 1 | Keyboard and rated supply | WK-220 reference-tested. Other models need their own MIDI receive evidence. |
| 0–1 | Ethernet cable | Preferred when convenient; Wi-Fi supported. |
| As needed | Reusable ties and pads | Secure cable slack to furniture or strain relief rather than pulling against sockets. |
| 0–1 | Touch Display 2, 7-inch, with matching stand/enclosure | [Manufacturer display](https://www.raspberrypi.com/products/touch-display-2/): 720×1280 native portrait, DSI and GPIO power. Use the Pi 5-specific cable and exact display revision's mounting instructions. Desktop rotation can provide landscape. |
| 0–1 | HDMI USB-touch display alternative | Requires video cable, USB touch data and specified supply. Do not reuse DSI housing/cable assumptions. |
| 0–1 | External backup target | Local or off-site storage configured using the backup guide. |

These are engineering selections checked against manufacturer documentation,
not a claim that an integrated touchscreen enclosure has been built or certified.

For a concrete integrated display option, the manufacturer's
[KKSB desktop enclosure, SKU 7350001162058](https://kksb-cases.com/collections/all/products/kksb-case-for-raspberry-pi-5-touch-display-2-desktop-orientation)
is specified for Pi 5 and the official 7-inch Touch Display 2. It supplies the
stand, angled feet and screws, with ventilation and interface access; electronics
and cooling are separate. It replaces the headless Pi case rather than enclosing
that case inside another. Select a low-profile cooler compatible with its internal
clearance and follow the linked manufacturer assembly instructions. Project fit
and loaded thermal validation of this option remain outstanding.

## Assembly, cabling and service access

1. Assemble the case/cooling with its supplied fixings. Leave ventilation open;
   do not place it under fabric or inside an unventilated piano.
2. Keep USB, microSD and the power button accessible. Measure bend clearance with
   the actual plugs and leave a removable service loop.
3. Route keyboard USB and power behind the stand with strain relief at both ends.
   Keep the module clear of pedals, knees and speakers.
4. Use a stable matching display stand that cannot tip under touch pressure.
   Protect the DSI ribbon; it is not a structural support.
5. Verify headless software and MIDI first, then add desktop/kiosk.
6. Check loaded temperature/throttling, plug clearance, service access and touch
   stability on the assembled unit before claiming physical validation.

Optional Play/Pause, Panic buttons and an encoder are not wired or supported by a
published GPIO service. Web transport supplies those actions. Reserve removable
space for a future control module; guessed pin assignments are not a working build.

Two-keyboard placement and acoustic synchronization remain deferred. Use one Pi
timeline and direct USB connections when that work resumes.

## Physical evidence still required

Issue #8 retains fit/thermal/serviceability validation and photographs of an actual
assembled touchscreen unit. Custom printable fabrication files are optional and
require correct mechanical drawings plus a fit check. The commercial-module
headless build above requires no project STL.

Continue with [Getting started](getting-started.md) and
[appliance installation](appliance-install.md).
