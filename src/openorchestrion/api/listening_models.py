"""Public, path-free schemas for the listening-room interface."""

from pydantic import BaseModel, ConfigDict

from .models import RenderingRequest


class ListeningModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrowseItem(ListeningModel):
    asset_id: str
    title: str | None
    composer: str | None
    artist: str | None
    performance_type: str | None
    duration_seconds: float
    favorite: bool
    source_label: str | None
    era: str | None


class BrowsePage(ListeningModel):
    items: list[BrowseItem]
    total: int
    offset: int
    limit: int
    has_more: bool


class BrowseFacet(ListeningModel):
    value: str
    count: int


class BrowseFacets(ListeningModel):
    eras: list[BrowseFacet]
    composers: list[BrowseFacet]
    sources: list[BrowseFacet]
    arrangements: list[BrowseFacet]
    genres: list[BrowseFacet]
    moods: list[BrowseFacet]
    total: int
    favorites: int


class EncodedInstrument(ListeningModel):
    channel: int
    gm_program_number: int
    gm_name: str
    bank_msb: int
    bank_lsb: int
    first_tick: int
    changes: int


class EncodedChannel(ListeningModel):
    channel: int
    is_percussion: bool


class PlaybackSound(ListeningModel):
    mapping_status: str
    mapping_note: str
    program: int
    name: str
    bank_msb: int
    bank_lsb: int
    implicit: bool
    note_count: int


class SourceTrack(ListeningModel):
    index: int
    name: str | None


class SoundingPart(ListeningModel):
    channel: int
    percussion: bool
    tracks: list[SourceTrack]
    sounds: list[PlaybackSound]
    note_count: int
    note_min: int
    note_max: int
    velocity_min: int
    velocity_max: int
    sustain: bool
    pitch_bend: bool
    peak_notes: int
    changed: bool


class ReadinessFlag(ListeningModel):
    code: str
    severity: str
    message: str


class SoundPalette(ListeningModel):
    kind: str
    label: str
    sounding_channels: int
    pitched_sound_count: int
    percussion: bool


class PlaybackReadiness(ListeningModel):
    source_palette: SoundPalette
    playback_palette: SoundPalette
    version: int
    status: str
    parts: list[SoundingPart]
    peak_notes: int
    flags: list[ReadinessFlag]
    limitation: str
    reference_device: str


class PerformancePreviewRequest(ListeningModel):
    rendering: RenderingRequest | None = None


class PerformancePreview(ListeningModel):
    rendering_mode: str
    readiness: PlaybackReadiness


class PerformanceDetail(ListeningModel):
    source_label: str | None
    source_reference: str | None
    license: str | None
    attribution: str | None
    rights_status: str
    midi_type: int
    ticks_per_beat: int
    track_count: int
    note_count: int
    note_min: int | None
    note_max: int | None
    velocity_min: int | None
    velocity_max: int | None
    sustain_used: bool
    pitch_bend_used: bool
    sysex_count: int
    peak_simultaneous_notes: int
    gm_assessment: str | None
    instruments: list[EncodedInstrument]
    channels: list[EncodedChannel]
