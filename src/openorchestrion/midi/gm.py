"""General MIDI names used for deterministic analysis/reporting and overrides."""

from __future__ import annotations

import re

GM_PROGRAM_NAMES = (
    "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone", "Marimba", "Xylophone",
    "Tubular Bells", "Dulcimer", "Drawbar Organ", "Percussive Organ", "Rock Organ",
    "Church Organ", "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
    "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar",
    "Guitar Harmonics", "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)",
    "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings",
    "Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2", "Synth Strings 1",
    "Synth Strings 2", "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet", "French Horn", "Brass Section",
    "Synth Brass 1", "Synth Brass 2", "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet", "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina", "Lead 1 (square)", "Lead 2 (sawtooth)",
    "Lead 3 (calliope)", "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
    "Lead 7 (fifths)", "Lead 8 (bass + lead)", "Pad 1 (new age)", "Pad 2 (warm)",
    "Pad 3 (polysynth)", "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)",
    "Pad 7 (halo)", "Pad 8 (sweep)", "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)",
    "FX 4 (atmosphere)", "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)",
    "FX 8 (sci-fi)", "Sitar", "Banjo", "Shamisen", "Koto", "Kalimba", "Bag Pipe", "Fiddle",
    "Shanai", "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock", "Taiko Drum", "Melodic Tom",
    "Synth Drum", "Reverse Cymbal", "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot",
)


class GMProgramError(ValueError):
    """A General MIDI program selector that is unknown or ambiguous."""


def _program_key(value: str) -> str:
    """Normalize punctuation/case without turning approximate families into programs."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


_PROGRAM_BY_NAME = {_program_key(name): number for number, name in enumerate(GM_PROGRAM_NAMES)}
# Deliberately tiny aliases. Family names such as ``strings`` or ``organ`` are
# ambiguous and must not silently select one patch. ``piano`` is the project's
# explicit default piano rendering and therefore has an unambiguous meaning.
_PROGRAM_ALIASES = {
    "piano": 0,
    "grandpiano": 0,
    "acousticgrand": 0,
}


def resolve_gm_program(value: int | str) -> int:
    """Resolve an internal MIDI program integer or a canonical GM patch name.

    Integer inputs are MIDI-native 0..127. String inputs are *names only*.
    Numeric strings are rejected so a future UI cannot accidentally confuse the
    human-facing GM patch numbers 1..128 with MIDI Program Change values 0..127.
    Punctuation and case are ignored for names: ``honky tonk piano`` resolves to
    the canonical ``Honky-tonk Piano``.
    """
    if isinstance(value, bool):
        raise GMProgramError("GM program must be an integer 0..127 or a program name")
    if isinstance(value, int):
        if not 0 <= value <= 127:
            raise GMProgramError("GM program integer must be between 0 and 127")
        return value
    if not isinstance(value, str):
        raise GMProgramError("GM program must be an integer 0..127 or a program name")

    text = value.strip()
    if not text:
        raise GMProgramError("GM program name cannot be blank")
    if text.isdecimal():
        raise GMProgramError(
            "numeric strings are ambiguous; use an integer 0..127 or a General MIDI program name"
        )
    key = _program_key(text)
    number = _PROGRAM_BY_NAME.get(key)
    if number is None:
        number = _PROGRAM_ALIASES.get(key)
    if number is None:
        raise GMProgramError(f"unknown or ambiguous General MIDI program name: {value!r}")
    return number


def gm_program_name(program: int) -> str:
    """Return the canonical General MIDI name for a MIDI-native program value."""
    number = resolve_gm_program(program)
    return GM_PROGRAM_NAMES[number]


CONTROLLER_NAMES = {
    0: "Bank Select MSB",
    1: "Modulation Wheel",
    7: "Channel Volume",
    10: "Pan",
    11: "Expression",
    32: "Bank Select LSB",
    64: "Sustain Pedal",
    91: "Reverb Send",
    93: "Chorus Send",
    120: "All Sound Off",
    121: "Reset All Controllers",
    123: "All Notes Off",
}
