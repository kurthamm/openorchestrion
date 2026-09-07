"""Load validated Mido messages while retaining unknown-meta delta times."""
from pathlib import Path

from mido import MidiFile
from mido.midifiles.meta import UnknownMetaMessage


def load_midi(path: str | Path) -> MidiFile:
    midi = MidiFile(path)
    if not any(isinstance(m, UnknownMetaMessage) for t in midi.tracks for m in t):
        return midi
    # Mido 1.3.x build_meta_message drops `delta` for unknown meta types.
    # Their payload is ignorable, their elapsed time is not. Recover only these
    # deltas from the original SMF; keep Mido's validation and all other messages.
    # Local import avoids the library importer -> analyzer dependency cycle.
    from ..library.midi_scan import read_events

    _, _, events = read_events(Path(path).read_bytes())
    previous = {}
    for tick, track, sequence, status, _ in events:
        delta = tick - previous.get(track, 0)
        previous[track] = tick
        message = midi.tracks[track][sequence]
        if status == 255 and isinstance(message, UnknownMetaMessage):
            message.time = delta
    return midi
