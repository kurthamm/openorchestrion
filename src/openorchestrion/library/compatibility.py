"""Read-only interpretation of sounding facts, independent of catalog labels.

WK-220 MIDI Implementation, sections 9.1 and 11:
https://support.casio.com/pdf/008/nil%20(MIDI_074M_E_1110A).pdf
No claim of verified vendor tones without the model's tone table.
"""
from __future__ import annotations


def sound_palette(parts: list[dict]) -> dict:
    """Describe encoded sounds, never infer performer count or completeness."""
    melodic = [p for p in parts if not p["percussion"]]
    drums = any(p["percussion"] for p in parts)
    sounds = [s for p in melodic for s in p["sounds"]]
    identities = {(s["program"], s["bank_msb"], s["bank_lsb"]) for s in sounds}
    if not parts:
        kind, label = "silent", "No sounding notes"
    elif not melodic:
        kind, label = "percussion_only", "Percussion only"
    elif any(s["bank_msb"] or s["bank_lsb"] for s in sounds):
        kind, label = "device_dependent", "Device-dependent instrument sounds"
    elif all(s["program"] in (1, 2) for s in sounds) and not drums:
        if any(s["implicit"] for s in sounds):
            kind, label = "piano_default", "Piano sounds, partly or entirely from player defaults"
        else:
            kind, label = "acoustic_piano", "Acoustic piano sounds only"
    elif len(identities) == 1 and not drums:
        kind, label = "single_instrument", "One instrument sound"
    else:
        kind, label = "multiple_instruments", "Multiple instrument sounds"
    return {"kind": kind, "label": label, "sounding_channels": len(parts),
            "pitched_sound_count": len(identities), "percussion": drums}


def annotate_wk220(parts: list[dict]) -> None:
    """Annotate a preview copy; retain exact source program and bank values."""
    for part in parts:
        for sound in part["sounds"]:
            uncertain = bool(sound["bank_msb"] or
                             (part["percussion"] and sound["program"] != 1))
            lsb = sound["bank_lsb"]
            sound["mapping_status"] = "unverified" if uncertain else "gm_baseline"
            notes = []
            if uncertain:
                notes.append("This bank/program combination has not been verified against the WK-220 tone list.")
            if lsb:
                notes.append(f"WK-220 ignores bank LSB {lsb}; any variation selected only by that value will not be reproduced.")
            if not notes:
                notes.append("Uses the player's General MIDI baseline; acoustic output has not been measured.")
            sound["mapping_note"] = " ".join(notes)
