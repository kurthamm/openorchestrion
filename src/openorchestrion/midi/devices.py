from __future__ import annotations

import mido


def list_output_ports() -> list[str]:
    """Return currently available MIDI output names."""
    return list(mido.get_output_names())


def find_output_port(match: str) -> str | None:
    """Find the first output port containing a case-insensitive match."""
    needle = match.casefold()
    for name in list_output_ports():
        if needle in name.casefold():
            return name
    return None
