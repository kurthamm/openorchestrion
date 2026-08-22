from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TempoChange:
    tick: int
    seconds: float
    tempo_us_per_beat: int
    bpm: float


@dataclass(frozen=True, slots=True)
class TimeSignatureChange:
    tick: int
    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class ProgramUse:
    tick: int
    channel: int
    program_zero_based: int
    gm_program_number: int
    gm_name: str
    bank_msb: int
    bank_lsb: int


@dataclass(frozen=True, slots=True)
class ControllerUse:
    controller: int
    name: str
    count: int
    channels: list[int]
    values: list[int]


@dataclass(frozen=True, slots=True)
class TrackAnalysis:
    index: int
    name: str | None
    event_count: int
    channels: list[int]
    note_count: int
    note_min: int | None
    note_max: int | None
    program_changes: int
    end_tick: int


@dataclass(frozen=True, slots=True)
class VelocityStats:
    count: int
    minimum: int | None
    maximum: int | None
    mean: float | None
    median: float | None
    histogram: dict[str, int]


@dataclass(frozen=True, slots=True)
class MidiAnalysis:
    source: str
    sha256: str | None
    file_size_bytes: int | None
    midi_type: int
    ticks_per_beat: int
    track_count: int
    duration_seconds: float
    tracks: list[TrackAnalysis]
    tempo_changes: list[TempoChange]
    time_signature_changes: list[TimeSignatureChange]
    channels: list[int]
    melodic_channels: list[int]
    percussion_channels: list[int]
    percussion_note_count: int
    note_count: int
    note_min: int | None
    note_max: int | None
    velocity: VelocityStats
    program_uses: list[ProgramUse]
    controllers: list[ControllerUse]
    sustain_used: bool
    pitch_bend_used: bool
    channel_aftertouch_used: bool
    poly_aftertouch_used: bool
    sysex_count: int
    peak_simultaneous_notes: int
    peak_simultaneous_notes_by_channel: dict[str, int]
    assessment: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
