from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mido import MidiFile, merge_tracks, tick2second

from .analysis_models import (
    ControllerUse,
    MidiAnalysis,
    ProgramUse,
    TempoChange,
    TimeSignatureChange,
    TrackAnalysis,
    VelocityStats,
)
from .gm import CONTROLLER_NAMES, GM_PROGRAM_NAMES

DEFAULT_TEMPO_US_PER_BEAT = 500_000


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _human_channel(channel_zero_based: int) -> int:
    return channel_zero_based + 1


def _track_analysis(midi: MidiFile) -> list[TrackAnalysis]:
    result: list[TrackAnalysis] = []
    for index, track in enumerate(midi.tracks):
        absolute_tick = 0
        name: str | None = None
        channels: set[int] = set()
        notes: list[int] = []
        program_changes = 0
        for message in track:
            absolute_tick += message.time
            if message.is_meta:
                if message.type == "track_name" and name is None:
                    name = message.name
                continue
            if hasattr(message, "channel"):
                channels.add(_human_channel(message.channel))
            if message.type == "note_on" and message.velocity > 0:
                notes.append(message.note)
            if message.type == "program_change":
                program_changes += 1
        result.append(
            TrackAnalysis(
                index=index,
                name=name,
                event_count=len(track),
                channels=sorted(channels),
                note_count=len(notes),
                note_min=min(notes) if notes else None,
                note_max=max(notes) if notes else None,
                program_changes=program_changes,
                end_tick=absolute_tick,
            )
        )
    return result


def _voice_peak(messages: list[Any]) -> tuple[int, dict[str, int]]:
    """Estimate peak simultaneous sounding notes.

    A sound engine allocates at most one voice per ``(channel, note)``: striking
    a pitch that is already sounding retriggers that voice rather than adding
    another. Occupancy is therefore modelled as *sets* of sounding notes, which
    makes double-counting structurally impossible — the previous counter-based
    version inflated without bound when a pitch was repeated under a held
    sustain pedal, and a pedal-heavy piano piece could report hundreds of voices
    where a real instrument sounds a handful.

    That figure gates device eligibility (``max_peak_simultaneous_notes``), so
    over-counting silently excluded exactly the solo-piano repertoire this
    project exists to play.

    Two stores per channel:

    * ``keyed``     — the key is physically down.
    * ``sustained`` — the key was released while the pedal was down, so the note
      keeps sounding until the pedal lifts.

    A note is in at most one store at a time; re-striking a sustained note moves
    it back under the key.
    """
    keyed: defaultdict[int, set[int]] = defaultdict(set)
    sustained: defaultdict[int, set[int]] = defaultdict(set)
    sustain_on: defaultdict[int, bool] = defaultdict(bool)

    current_total = 0
    peak_total = 0
    peak_by_channel: Counter[int] = Counter()

    def occupancy(channel: int) -> int:
        return len(keyed[channel]) + len(sustained[channel])

    def observe(channel: int, before: int) -> None:
        """Fold one channel's change into the running totals.

        Deriving the delta from set sizes keeps the total exact no matter how
        the sets were mutated, which is what the counter arithmetic got wrong.
        """
        nonlocal current_total, peak_total
        after = occupancy(channel)
        current_total += after - before
        peak_total = max(peak_total, current_total)
        peak_by_channel[channel] = max(peak_by_channel[channel], after)

    for message in messages:
        if message.is_meta:
            continue

        if message.type == "note_on" and message.velocity > 0:
            channel = message.channel
            before = occupancy(channel)
            # Retrigger in place: a pitch already sounding claims no new voice,
            # and a sustained note comes back under the key.
            sustained[channel].discard(message.note)
            keyed[channel].add(message.note)
            observe(channel, before)
            continue

        if message.type in {"note_off", "note_on"}:
            channel = message.channel
            if message.note not in keyed[channel]:
                continue
            before = occupancy(channel)
            keyed[channel].discard(message.note)
            if sustain_on[channel]:
                sustained[channel].add(message.note)
            observe(channel, before)
            continue

        if message.type != "control_change":
            continue

        channel = message.channel
        before = occupancy(channel)

        if message.control == 64:
            sustain_on[channel] = message.value >= 64
            if not sustain_on[channel]:
                sustained[channel].clear()
        elif message.control == 120:
            # All Sound Off: silence immediately, pedal included.
            keyed[channel].clear()
            sustained[channel].clear()
            sustain_on[channel] = False
        elif message.control == 123:
            # All Notes Off releases the keys. Notes the pedal is holding keep
            # sounding until it lifts, exactly as releasing every key by hand
            # would; only treating this as instant silence would under-count.
            if sustain_on[channel]:
                sustained[channel].update(keyed[channel])
            keyed[channel].clear()
        elif message.control == 121:
            # Reset All Controllers returns the pedal to its default (up).
            sustain_on[channel] = False
            sustained[channel].clear()
        else:
            continue

        observe(channel, before)

    return peak_total, {
        str(_human_channel(channel)): peak_by_channel[channel]
        for channel in sorted(peak_by_channel)
    }


def analyze_midifile(
    midi: MidiFile,
    *,
    source: str = "<memory>",
    sha256: str | None = None,
    file_size_bytes: int | None = None,
) -> MidiAnalysis:
    merged = list(merge_tracks(midi.tracks))
    tempo = DEFAULT_TEMPO_US_PER_BEAT
    absolute_tick = 0
    elapsed_seconds = 0.0

    tempo_changes: list[TempoChange] = []
    time_signatures: list[TimeSignatureChange] = []
    channels: set[int] = set()
    notes: list[int] = []
    velocities: list[int] = []
    percussion_note_count = 0
    programs: list[ProgramUse] = []
    bank_msb: defaultdict[int, int] = defaultdict(int)
    bank_lsb: defaultdict[int, int] = defaultdict(int)
    controller_counter: Counter[int] = Counter()
    controller_channels: defaultdict[int, set[int]] = defaultdict(set)
    controller_values: defaultdict[int, set[int]] = defaultdict(set)
    sustain_used = False
    pitch_bend_used = False
    channel_aftertouch_used = False
    poly_aftertouch_used = False
    sysex_count = 0

    for message in merged:
        delta_ticks = message.time
        elapsed_seconds += tick2second(delta_ticks, midi.ticks_per_beat, tempo)
        absolute_tick += delta_ticks

        if message.is_meta:
            if message.type == "set_tempo":
                tempo = message.tempo
                tempo_changes.append(
                    TempoChange(
                        tick=absolute_tick,
                        seconds=round(elapsed_seconds, 9),
                        tempo_us_per_beat=tempo,
                        bpm=round(60_000_000 / tempo, 6),
                    )
                )
            elif message.type == "time_signature":
                time_signatures.append(
                    TimeSignatureChange(
                        tick=absolute_tick,
                        numerator=message.numerator,
                        denominator=message.denominator,
                    )
                )
            continue

        if message.type == "sysex":
            sysex_count += 1
            continue

        if hasattr(message, "channel"):
            channels.add(_human_channel(message.channel))

        if message.type == "note_on" and message.velocity > 0:
            notes.append(message.note)
            velocities.append(message.velocity)
            if message.channel == 9:
                percussion_note_count += 1
        elif message.type == "control_change":
            controller_counter[message.control] += 1
            controller_channels[message.control].add(_human_channel(message.channel))
            controller_values[message.control].add(message.value)
            if message.control == 0:
                bank_msb[message.channel] = message.value
            elif message.control == 32:
                bank_lsb[message.channel] = message.value
            elif message.control == 64 and message.value >= 64:
                sustain_used = True
        elif message.type == "program_change":
            program = message.program
            programs.append(
                ProgramUse(
                    tick=absolute_tick,
                    channel=_human_channel(message.channel),
                    program_zero_based=program,
                    gm_program_number=program + 1,
                    gm_name=GM_PROGRAM_NAMES[program],
                    bank_msb=bank_msb[message.channel],
                    bank_lsb=bank_lsb[message.channel],
                )
            )
        elif message.type == "pitchwheel":
            pitch_bend_used = True
        elif message.type == "aftertouch":
            channel_aftertouch_used = True
        elif message.type == "polytouch":
            poly_aftertouch_used = True

    if not tempo_changes:
        tempo_changes.append(
            TempoChange(
                tick=0,
                seconds=0.0,
                tempo_us_per_beat=DEFAULT_TEMPO_US_PER_BEAT,
                bpm=120.0,
            )
        )

    velocity_histogram = Counter(velocities)
    velocity_stats = VelocityStats(
        count=len(velocities),
        minimum=min(velocities) if velocities else None,
        maximum=max(velocities) if velocities else None,
        mean=round(statistics.mean(velocities), 3) if velocities else None,
        median=round(statistics.median(velocities), 3) if velocities else None,
        histogram={str(value): velocity_histogram[value] for value in sorted(velocity_histogram)},
    )

    controller_uses = [
        ControllerUse(
            controller=controller,
            name=CONTROLLER_NAMES.get(controller, f"CC {controller}"),
            count=controller_counter[controller],
            channels=sorted(controller_channels[controller]),
            values=sorted(controller_values[controller]),
        )
        for controller in sorted(controller_counter)
    ]

    peak_total, peak_channels = _voice_peak(merged)
    nonzero_bank_select = any(
        value != 0
        for controller in (0, 32)
        for value in controller_values.get(controller, set())
    )
    percussion_channels = [10] if 10 in channels and percussion_note_count else []
    melodic_channels = sorted(channel for channel in channels if channel != 10)

    if nonzero_bank_select:
        gm_assessment = "extended-or-device-specific-bank"
    elif programs or percussion_note_count:
        gm_assessment = "gm-compatible-structure"
    else:
        gm_assessment = "undetermined"

    assessment: dict[str, Any] = {
        "gm_assessment": gm_assessment,
        "uses_channel_10_percussion": bool(percussion_note_count),
        "uses_nonzero_bank_select": nonzero_bank_select,
        "uses_sysex": sysex_count > 0,
        "uses_sustain": sustain_used,
        "uses_pitch_bend": pitch_bend_used,
        "uses_aftertouch": channel_aftertouch_used or poly_aftertouch_used,
        "peak_over_24": peak_total > 24,
        "peak_over_32": peak_total > 32,
        "peak_over_48": peak_total > 48,
        "peak_over_64": peak_total > 64,
        "full_midi_note_range_exercised": bool(notes) and min(notes) == 0 and max(notes) == 127,
        "type_2_asynchronous": midi.type == 2,
        "tempo_changes": (
            max(0, len(tempo_changes) - 1)
            if tempo_changes and tempo_changes[0].tick == 0
            else len(tempo_changes)
        ),
        "time_signature_changes": (
            max(0, len(time_signatures) - 1)
            if time_signatures and time_signatures[0].tick == 0
            else len(time_signatures)
        ),
        "peak_note_estimate_note": (
            "Estimated simultaneous MIDI notes, not manufacturer oscillator/sample voice usage."
        ),
    }

    return MidiAnalysis(
        source=source,
        sha256=sha256,
        file_size_bytes=file_size_bytes,
        midi_type=midi.type,
        ticks_per_beat=midi.ticks_per_beat,
        track_count=len(midi.tracks),
        duration_seconds=round(elapsed_seconds, 6),
        tracks=_track_analysis(midi),
        tempo_changes=tempo_changes,
        time_signature_changes=time_signatures,
        channels=sorted(channels),
        melodic_channels=melodic_channels,
        percussion_channels=percussion_channels,
        percussion_note_count=percussion_note_count,
        note_count=len(notes),
        note_min=min(notes) if notes else None,
        note_max=max(notes) if notes else None,
        velocity=velocity_stats,
        program_uses=programs,
        controllers=controller_uses,
        sustain_used=sustain_used,
        pitch_bend_used=pitch_bend_used,
        channel_aftertouch_used=channel_aftertouch_used,
        poly_aftertouch_used=poly_aftertouch_used,
        sysex_count=sysex_count,
        peak_simultaneous_notes=peak_total,
        peak_simultaneous_notes_by_channel=peak_channels,
        assessment=assessment,
    )


def analyze_midi(path: str | Path) -> MidiAnalysis:
    source_path = Path(path)
    midi = MidiFile(source_path)
    return analyze_midifile(
        midi,
        source=str(source_path),
        sha256=_sha256(source_path),
        file_size_bytes=source_path.stat().st_size,
    )


def _duration_text(seconds: float) -> str:
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{sec:05.2f}"
    return f"{minutes:02d}:{sec:05.2f}"


def format_analysis(analysis: MidiAnalysis) -> str:
    lines = [
        "OpenOrchestrion MIDI analysis",
        f"File: {analysis.source}",
        f"SHA-256: {analysis.sha256 or 'n/a'}",
        f"SMF type: {analysis.midi_type}",
        f"Ticks/beat: {analysis.ticks_per_beat}",
        f"Tracks: {analysis.track_count}",
        f"Duration: {_duration_text(analysis.duration_seconds)}",
        f"Channels: {', '.join(map(str, analysis.channels)) or 'none'}",
        f"Notes: {analysis.note_count}",
        f"Note range: {analysis.note_min if analysis.note_min is not None else 'n/a'}"
        f"–{analysis.note_max if analysis.note_max is not None else 'n/a'}",
        (
            "Velocity: "
            f"{analysis.velocity.minimum if analysis.velocity.minimum is not None else 'n/a'}–"
            f"{analysis.velocity.maximum if analysis.velocity.maximum is not None else 'n/a'} "
            f"(mean {analysis.velocity.mean if analysis.velocity.mean is not None else 'n/a'})"
        ),
        f"Peak simultaneous MIDI notes: {analysis.peak_simultaneous_notes}",
        f"Percussion channel 10: {'yes' if analysis.percussion_note_count else 'no'}",
        f"Sustain CC64: {'yes' if analysis.sustain_used else 'no'}",
        f"GM assessment: {analysis.assessment['gm_assessment']}",
    ]

    if analysis.program_uses:
        lines.append("Programs:")
        seen: set[tuple[int, int, int, int]] = set()
        for program in analysis.program_uses:
            key = (
                program.channel,
                program.program_zero_based,
                program.bank_msb,
                program.bank_lsb,
            )
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"  Ch {program.channel:>2}  {program.gm_program_number:>3} "
                f"{program.gm_name}  bank {program.bank_msb}/{program.bank_lsb}"
            )

    if analysis.controllers:
        lines.append("Controllers:")
        for controller in analysis.controllers:
            lines.append(
                f"  CC {controller.controller:>3} {controller.name}: "
                f"{controller.count} event(s), values {controller.values}"
            )

    if any(
        (analysis.pitch_bend_used, analysis.channel_aftertouch_used, analysis.poly_aftertouch_used)
    ):
        lines.append(
            "Expressive events: "
            f"pitch-bend={'yes' if analysis.pitch_bend_used else 'no'}, "
            f"channel-aftertouch={'yes' if analysis.channel_aftertouch_used else 'no'}, "
            f"poly-aftertouch={'yes' if analysis.poly_aftertouch_used else 'no'}"
        )

    if analysis.sysex_count:
        lines.append(f"SysEx messages: {analysis.sysex_count}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a Standard MIDI File deterministically.")
    parser.add_argument("midi_file", help="Path to a .mid file")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    analysis = analyze_midi(args.midi_file)
    if args.json:
        print(json.dumps(analysis.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_analysis(analysis))


if __name__ == "__main__":
    main()
