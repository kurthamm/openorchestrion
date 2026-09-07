# Source sound palettes and WK-220 compatibility

7 September 2026. See the [quality definition and research](library-quality-standard.md)
before treating structural evidence as a musical-quality verdict.

The performance-preview API now adds `source_palette` and `playback_palette`,
each with `kind`, `label`, `sounding_channels`, `pitched_sound_count` and
`percussion`. Sound records add `mapping_status` and `mapping_note`. Palette
classification describes requested sounds, not performer count or completeness.
Raw facts remain version 1: these fields are computed projections, so the
existing source-facts index does not need rebuilding.

Explicit bank-zero acoustic piano programs 1/2, implicit piano defaults,
percussion-only sources, other single sounds, multiple sounds and device-dependent
banks are distinguished. Multiple channels playing piano can still be a piano
palette; one channel changing instruments can contain multiple sounds.

Casio's [WK-220 implementation, section 9.1](https://support.casio.com/pdf/008/nil%20(MIDI_074M_E_1110A).pdf)
documents ignored bank LSB. The preview identifies this known limitation per
sound and with `wk220_bank_lsb_ignored`, separately from unverified vendor
banks/kits. `gm_baseline` describes the player's baseline, not measured tone
fidelity. Original program/bank values remain visible and unchanged. Warnings
are projected after rendering overrides, while the source palette is preserved.

Validation: 681 Python tests; Ruff E4/E7/E9/F; repository contracts; browser
state checks; installed-wheel virtual-server smoke; actual Kyosuke I details
rendered in an isolated browser preview. All-library audit: 20,549 assets,
zero mutations. Reports are under `docs/evidence/library-compatibility/`.

Built and tested wheel SHA-256:
`d40aa966b1eb1a9d2976a4833432c6281f801469cce52742dfd3214902fe472a`.
This wheel is **not deployed**. The live queue changed during this work and its
saved rendering setting is not exposed by the current API; avoid restoring it
with a guessed setting. Coordinate installation with the persistence developer
or an empty queue. Existing live release and admission remain unchanged.

No engine, queue, transport, playlist, sleep or persistence implementation was
changed. No hardware audition or new endurance result is claimed.
