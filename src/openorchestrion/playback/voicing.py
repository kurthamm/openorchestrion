"""Automatic voicing for orchestral score exports.

Engraving tools such as LilyPond write General MIDI programs per part, and the
choices are often poor for a hardware tone generator: every string section on a
*solo* string patch, horns on English Horn, or no Program Change at all so an
entire orchestra plays as twelve pianos.  On a keyboard those sustained block
chords blur into an organ-like wash.

This module looks only at the deterministic analysis already stored in an
asset's sidecar and proposes per-channel program overrides.  It is deliberately
conservative: nothing is suggested unless the file looks like an orchestral
score, so chamber music that legitimately uses solo strings is left alone.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from openorchestrion.midi.gm import resolve_gm_program

PERCUSSION_CHANNEL = 9

# The stored analysis numbers channels 1..16 as musicians read them; rendering
# overrides use MIDI-native 0..15.  Convert once, at this boundary.
def _midi_channel(value: Any) -> int:
    return int(value) - 1

SOLO_STRINGS = frozenset({40, 41, 42, 43})
STRING_ENSEMBLE = resolve_gm_program("String Ensemble 1")
FRENCH_HORN = resolve_gm_program("French Horn")
ENGLISH_HORN = resolve_gm_program("English Horn")
PIANO = 0

#: Programs whose presence says "this is an orchestra, not a piano piece".
ORCHESTRAL_PROGRAMS = frozenset(range(56, 80)) | {47}  # brass, reeds, pipes, timpani

#: Part names an engraver typically leaves in track names, mapped to the GM
#: program a hardware engine should use for that part in an orchestral context.
_NAME_HINTS: tuple[tuple[re.Pattern[str], int], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), resolve_gm_program(program))
    for pattern, program in (
        (r"\bpicc", "Piccolo"),
        (r"\b(flute|flauto|fl\.?)\b", "Flute"),
        (r"\b(oboe|hautbois|ob\.?)\b", "Oboe"),
        (r"\b(english horn|cor anglais|corno inglese)\b", "English Horn"),
        (r"\b(clarinet|clarinetto|klarinette|cl\.?)\b", "Clarinet"),
        (r"\b(bassoon|fagott|fagotto|bsn\.?|fag\.?)\b", "Bassoon"),
        (r"\b(horn|corno|corni|cor|hn\.?)\b", "French Horn"),
        (r"\b(trumpet|tromba|trombe|clarino|tpt\.?)\b", "Trumpet"),
        (r"\b(trombone|tromboni|posaune|tbn\.?)\b", "Trombone"),
        (r"\btuba\b", "Tuba"),
        (r"\b(timpani|timp\.?|pauken)\b", "Timpani"),
        (r"\b(harp|arpa)\b", "Orchestral Harp"),
        (r"\b(violin|violino|violini|vln\.?|vl\.?)\b", "String Ensemble 1"),
        (r"\b(viola|viole|vla\.?)\b", "String Ensemble 1"),
        (r"\b(cello|violoncello|violoncelli|vc\.?|vcl\.?)\b", "String Ensemble 1"),
        (r"\b(contrabass\w*|double bass|basso|bassi|cb\.?|kb\.?)\b", "String Ensemble 1"),
        (r"\b(choir|chorus|coro|soprano|alto|tenor|bass voice)\b", "Choir Aahs"),
    )
)
_ENGLISH_HORN_NAME = re.compile(r"english|anglais|inglese", re.IGNORECASE)
_HORN_NAME = re.compile(r"\b(horn|corno|corni|cor|hn\.?)\b", re.IGNORECASE)


def _first_program_by_channel(analysis: Mapping[str, Any]) -> dict[int, int]:
    first: dict[int, int] = {}
    for use in sorted(analysis.get("program_uses", ()), key=lambda u: (int(u["tick"]), _midi_channel(u["channel"]))):
        first.setdefault(_midi_channel(use["channel"]), int(use["program_zero_based"]))
    return first


def _names_by_channel(analysis: Mapping[str, Any]) -> dict[int, list[str]]:
    names: dict[int, list[str]] = {}
    for track in analysis.get("tracks", ()):
        name = (track.get("name") or "").strip()
        if not name or not track.get("note_count"):
            continue
        for channel in track.get("channels", ()):
            names.setdefault(_midi_channel(channel), []).append(name)
    return names


def _hinted_program(names: Iterable[str]) -> int | None:
    for name in names:
        for pattern, program in _NAME_HINTS:
            if pattern.search(name):
                return program
    return None


def looks_orchestral(analysis: Mapping[str, Any]) -> bool:
    """Six or more pitched parts and at least one wind, brass or timpani voice."""
    pitched = [_midi_channel(c) for c in analysis.get("melodic_channels", ()) if _midi_channel(c) != PERCUSSION_CHANNEL]
    if len(pitched) < 6:
        return False
    programs = _first_program_by_channel(analysis)
    if any(programs.get(channel, PIANO) in ORCHESTRAL_PROGRAMS for channel in pitched):
        return True
    names = _names_by_channel(analysis)
    return any((_hinted_program(names.get(channel, ())) or -1) in ORCHESTRAL_PROGRAMS for channel in pitched)


def suggest_program_overrides(analysis: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    """Per-channel ``(channel, gm_program)`` corrections, or nothing for non-orchestral files."""
    if not looks_orchestral(analysis):
        return ()
    programs = _first_program_by_channel(analysis)
    names = _names_by_channel(analysis)
    overrides: dict[int, int] = {}
    for channel in sorted(_midi_channel(c) for c in analysis.get("melodic_channels", ())):
        if channel == PERCUSSION_CHANNEL:
            continue
        # Auto must not flatten instrument changes or erase a device-specific
        # bank. Explicit user overrides remain available through the renderer.
        uses = [u for u in analysis.get("program_uses", ())
                if _midi_channel(u["channel"]) == channel]
        states = {(int(u.get("bank_msb", 0)), int(u.get("bank_lsb", 0)),
                   int(u["program_zero_based"])) for u in uses}
        if len(states) > 1 or any(msb or lsb for msb, lsb, _ in states):
            continue
        program = programs.get(channel, PIANO)
        part_names = names.get(channel, [])
        if program in SOLO_STRINGS:
            overrides[channel] = STRING_ENSEMBLE
        elif program == ENGLISH_HORN and any(
            _HORN_NAME.search(n) and not _ENGLISH_HORN_NAME.search(n) for n in part_names
        ):
            overrides[channel] = FRENCH_HORN
        elif program == PIANO:
            hinted = _hinted_program(part_names)
            if hinted is not None:
                overrides[channel] = hinted
    return tuple(sorted((channel, program) for channel, program in overrides.items() if programs.get(channel, PIANO) != program))


__all__ = ["looks_orchestral", "suggest_program_overrides"]
