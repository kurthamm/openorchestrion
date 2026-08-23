"""Peak simultaneous note estimation.

``peak_simultaneous_notes`` gates device eligibility through
``StationConstraints.max_peak_simultaneous_notes``, so an over-count does not
merely mis-report — it silently removes music from stations. The original
counter inflated without bound when a pitch was repeated under a held sustain
pedal, which is ordinary piano writing, so pedal-heavy solo repertoire was
excluded on a 48-voice instrument.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from mido import Message, MetaMessage, MidiFile, MidiTrack

from openorchestrion.library.catalog import rebuild_catalog, search_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.metadata import (
    read_metadata,
    sidecar_path,
    update_metadata,
)
from openorchestrion.midi.analyzer import analyze_midi, analyze_midifile
from openorchestrion.stations import StationConstraints, build_station
from openorchestrion.models import PlaybackIntent
from openorchestrion.testing.midi_fixtures import generate_suite


def build(*events: Message) -> MidiFile:
    midi = MidiFile(type=1, ticks_per_beat=480)
    track = MidiTrack()
    midi.tracks.append(track)
    track.append(MetaMessage("set_tempo", tempo=500000, time=0))
    track.extend(events)
    return midi


def peak(*events: Message) -> int:
    return analyze_midifile(build(*events)).peak_simultaneous_notes


def pedal(down: bool, channel: int = 0) -> Message:
    return Message("control_change", channel=channel, control=64, value=127 if down else 0, time=0)


def strike(note: int, channel: int = 0, time: int = 0) -> Message:
    return Message("note_on", channel=channel, note=note, velocity=90, time=time)


def release(note: int, channel: int = 0, time: int = 0) -> Message:
    return Message("note_off", channel=channel, note=note, velocity=0, time=time)


# ------------------------------------------------------------- the defect


def test_a_repeated_pitch_under_pedal_claims_one_voice() -> None:
    """The reported bug: 40 strikes of one note read as 40 simultaneous voices."""
    events = [pedal(True)]
    for index in range(40):
        events.append(strike(60, time=0 if index == 0 else 120))
        events.append(release(60, time=60))
    assert peak(*events) <= 2


def test_a_repeated_pitch_without_pedal_also_claims_one_voice() -> None:
    events = []
    for index in range(20):
        events.append(strike(60, time=0 if index == 0 else 120))
        events.append(release(60, time=60))
    assert peak(*events) == 1


def test_a_pitch_restruck_before_release_does_not_stack() -> None:
    """Overlapping note_on for the same pitch retriggers one voice."""
    assert peak(strike(60), strike(60), strike(60)) == 1


# ------------------------------------------------- genuine polyphony still counts


def test_a_real_chord_under_pedal_counts_every_pitch() -> None:
    events = [pedal(True)]
    events += [strike(note) for note in (60, 64, 67, 72)]
    events += [release(note, time=10) for note in (60, 64, 67, 72)]
    assert peak(*events) == 4


def test_the_pedal_holds_released_notes_until_it_lifts() -> None:
    """Four notes played one at a time under the pedal are four voices."""
    events = [pedal(True)]
    for note in (60, 64, 67, 72):
        events.append(strike(note, time=10))
        events.append(release(note, time=10))
    assert peak(*events) == 4


def test_lifting_the_pedal_frees_the_voices() -> None:
    events = [pedal(True)]
    for note in (60, 64, 67, 72):
        events.append(strike(note, time=10))
        events.append(release(note, time=10))
    events.append(pedal(False))
    events.append(strike(48, time=10))
    # The later single note does not add to the earlier four.
    assert peak(*events) == 4


def test_polyphony_is_summed_across_channels() -> None:
    events = [strike(60 + index, channel=index) for index in range(4)]
    assert peak(*events) == 4


# ------------------------------------------------------ controller semantics


def test_all_notes_off_leaves_pedal_held_notes_sounding() -> None:
    """CC 123 releases the keys; the pedal keeps its notes until it lifts.

    Treating it as instant silence would under-count, which fails the other way
    — admitting music a device cannot actually play.
    """
    events = [pedal(True), strike(60), strike(64), strike(67)]
    events.append(Message("control_change", channel=0, control=123, value=0, time=10))
    events.append(strike(72, time=10))
    assert peak(*events) == 4


def test_all_sound_off_silences_everything_including_the_pedal() -> None:
    events = [pedal(True), strike(60), strike(64), strike(67)]
    events.append(Message("control_change", channel=0, control=120, value=0, time=10))
    events.append(strike(72, time=10))
    assert peak(*events) == 3  # the earlier chord, not 4


def test_reset_all_controllers_lifts_the_pedal() -> None:
    events = [pedal(True), strike(60), release(60, time=10)]
    events.append(Message("control_change", channel=0, control=121, value=0, time=10))
    events.append(strike(64, time=10))
    assert peak(*events) == 1


def test_a_note_off_for_a_pitch_never_struck_is_ignored() -> None:
    assert peak(release(60), strike(64)) == 1


def test_controllers_on_one_channel_do_not_affect_another() -> None:
    events = [
        pedal(True, channel=0),
        strike(60, channel=0),
        release(60, channel=0, time=10),
        strike(64, channel=1),
        Message("control_change", channel=1, control=120, value=0, time=10),
        strike(67, channel=1, time=10),
    ]
    # Channel 0 keeps its pedal-held note throughout.
    assert peak(*events) == 2


# ------------------------------------------------------------- the fixtures


@pytest.mark.parametrize("voices", [16, 32, 48, 64])
def test_polyphony_fixtures_report_their_designed_voice_count(
    tmp_path: Path, voices: int
) -> None:
    """The conformance suite is the acceptance check: these must not move."""
    generate_suite(tmp_path, long_run_minutes=1)
    analysis = analyze_midi(tmp_path / f"polyphony-{voices}.mid")
    assert analysis.peak_simultaneous_notes == voices


def test_sustain_fixture_reports_its_three_note_chord(tmp_path: Path) -> None:
    generate_suite(tmp_path, long_run_minutes=1)
    assert analyze_midi(tmp_path / "sustain-cc64.mid").peak_simultaneous_notes == 3


# ------------------------------------------------- the reason it matters


def test_a_pedal_heavy_piece_is_no_longer_excluded_by_a_device_limit(
    tmp_path: Path,
) -> None:
    """The whole point: a 48-voice keyboard must still admit piano repertoire."""
    source = tmp_path / "sources"
    source.mkdir()
    events = [pedal(True)]
    for index in range(60):
        events.append(strike(60 + (index % 3), time=0 if index == 0 else 60))
        events.append(release(60 + (index % 3), time=30))
    build(*events).save(source / "pedal-heavy.mid")

    library = tmp_path / "library"
    assert not import_paths([source], library).failed
    rebuild_catalog(library)

    asset = search_catalog(library / "catalog.db", limit=1)[0]
    assert asset["peak_simultaneous_notes"] <= 3

    queue = build_station(
        library / "catalog.db",
        PlaybackIntent(),
        constraints=StationConstraints(max_peak_simultaneous_notes=48),
    )
    assert [item.asset_id for item in queue.items] == [asset["asset_id"]]


# --------------------------------------------------------- repair migration


@pytest.fixture
def stale_library(tmp_path: Path) -> Path:
    """A library carrying the inflated values a pre-fix import would have left."""
    fixtures = tmp_path / "fixtures"
    generate_suite(fixtures, long_run_minutes=1)
    library = tmp_path / "library"
    assert not import_paths([fixtures], library).failed

    for sidecar in (library / "assets").glob("*.json"):
        document = json.loads(sidecar.read_text())
        document["deterministic_analysis"]["peak_simultaneous_notes"] = 512
        sidecar.write_text(json.dumps(document, indent=2, sort_keys=True))
    rebuild_catalog(library)
    return library


def _reanalyze(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "openorchestrion.library.repair", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_repair_corrects_stale_values_across_the_library(stale_library: Path) -> None:
    before = {row["peak_simultaneous_notes"] for row in search_catalog(
        stale_library / "catalog.db", limit=1000
    )}
    assert before == {512}

    result = _reanalyze("--library-root", str(stale_library))
    assert result.returncode == 0, result.stderr

    after = {row["peak_simultaneous_notes"] for row in search_catalog(
        stale_library / "catalog.db", limit=1000
    )}
    assert 512 not in after
    assert {16, 32, 48, 64}.issubset(after)


def test_repair_preserves_curated_metadata(stale_library: Path) -> None:
    """Re-analysis replaces derived facts only; human judgement survives."""
    asset_id = search_catalog(stale_library / "catalog.db", limit=1)[0]["asset_id"]
    update_metadata(
        stale_library,
        asset_id,
        {"title": "Curated Before Repair", "composer": "Kept", "favorite": True},
    )
    provenance = json.loads(sidecar_path(stale_library, asset_id).read_text())["provenance"]

    assert _reanalyze("--library-root", str(stale_library)).returncode == 0

    stored = read_metadata(stale_library, asset_id).descriptive_metadata
    assert stored["title"] == "Curated Before Repair"
    assert stored["favorite"] is True
    document = json.loads(sidecar_path(stale_library, asset_id).read_text())
    assert document["provenance"] == provenance
    assert document["deterministic_analysis"]["peak_simultaneous_notes"] != 512


def test_repair_of_a_single_asset(stale_library: Path) -> None:
    asset_id = search_catalog(stale_library / "catalog.db", limit=1)[0]["asset_id"]
    result = _reanalyze(asset_id, "--library-root", str(stale_library))
    assert result.returncode == 0, result.stderr
    document = json.loads(sidecar_path(stale_library, asset_id).read_text())
    assert document["deterministic_analysis"]["peak_simultaneous_notes"] != 512


def test_repair_reports_an_unknown_asset(stale_library: Path) -> None:
    result = _reanalyze("sha256:" + "0" * 64, "--library-root", str(stale_library))
    assert result.returncode == 2
    assert "error:" in result.stderr
