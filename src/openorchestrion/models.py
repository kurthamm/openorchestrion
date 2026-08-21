from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class PerformanceType(StrEnum):
    SOLO_PIANO = "SOLO_PIANO"
    MULTI_INSTRUMENT = "MULTI_INSTRUMENT"
    PIANO_DUET = "PIANO_DUET"
    TWO_PIANO = "TWO_PIANO"
    DUELING_PIANO = "DUELING_PIANO"
    DISTRIBUTED = "DISTRIBUTED"


class PlaybackIntent(BaseModel):
    """Validated interpretation of a user request.

    AI providers may suggest this object, but the deterministic application
    validates and executes it. Providers never receive direct MIDI access.
    """

    mode: Literal["station", "queue", "single", "modify_current"] = "station"
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    genres: list[str] = []
    moods: list[str] = []
    themes: list[str] = []
    eras: list[str] = []
    composers: list[str] = []
    artists: list[str] = []
    instrumentation: list[str] = []
    performance_types: list[PerformanceType] = []
    familiarity: Literal["low", "medium", "high"] | None = None
    energy: Literal["low", "medium", "high"] | None = None
    tempo_preference: Literal["slow", "medium", "fast", "mixed"] | None = None
    include_tags: list[str] = []
    exclude_tags: list[str] = []
    avoid_recent_repeats: bool = True
    repeat_window_days: int | None = Field(default=30, ge=0, le=3650)
    device_preferences: list[str] = []
    routing_preferences: dict[str, str] = {}
    continuation_behavior: Literal["replace", "refine", "append"] | None = None
    interpretation: str | None = Field(default=None, max_length=500)


class DeviceProfile(BaseModel):
    id: str
    manufacturer: str
    model: str
    midi_receive: bool
    transport: Literal["usb-midi", "din-midi", "network-midi", "other"]
    status: Literal["documented", "community-tested", "project-validated"] = "documented"
    general_midi: bool | None = None
    multitimbral_parts: int | None = None
    max_polyphony: int | None = None
    note_receive_min: int | None = Field(default=None, ge=0, le=127)
    note_receive_max: int | None = Field(default=None, ge=0, le=127)
    supports_velocity: bool | None = None
    supports_sustain_cc64: bool | None = None
    supports_program_change: bool | None = None
    supports_bank_select: bool | None = None
    built_in_speakers: bool | None = None
    latency_offset_ms: float = 0.0
    preferred_instrument_families: list[str] = []
    notes: str | None = None
