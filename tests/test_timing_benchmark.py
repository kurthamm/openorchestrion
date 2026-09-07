from __future__ import annotations

import pytest
from mido import Message, MidiFile, MidiTrack

from openorchestrion.playback.benchmark import (
    CapturedSend,
    ExpectedSend,
    TimingTargets,
    _capture,
    _failures,
    _run_case,
    summarize_skew,
    summarize_timing,
)
from openorchestrion.playback.clock import ManualClock
from openorchestrion.playback.outputs import MidiOutputRouter, VirtualMidiOutput


@pytest.mark.asyncio
async def test_capture_excludes_real_router_startup_and_cleanup_messages() -> None:
    clock = ManualClock()
    output = VirtualMidiOutput("A", clock)
    router = MidiOutputRouter([output])
    await router.reset_channels()
    await output.send(Message("note_on", channel=0, note=60))
    await clock.advance(0.25)
    await output.send(Message("note_off", channel=0, note=60))
    await router.panic()
    expected = [ExpectedSend(0, "note_on", 0, 60), ExpectedSend(0.25, "note_off", 0, 60)]
    captured = _capture(expected, output)
    assert [item.actual_seconds for item in captured] == [0, 0.25]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing", "extra", "wrong_note"])
async def test_capture_rejects_corrupted_note_sequence(fault: str) -> None:
    output = VirtualMidiOutput("A", ManualClock())
    if fault != "missing":
        await output.send(Message("note_on", note=61 if fault == "wrong_note" else 60))
    if fault == "extra":
        await output.send(Message("note_on", note=60))
    with pytest.raises(RuntimeError, match="captured|does not match"):
        _capture([ExpectedSend(0, "note_on", 0, 60)], output)


@pytest.mark.asyncio
async def test_benchmark_captures_notes_from_full_engine_lifecycle(tmp_path) -> None:
    midi = MidiFile()
    midi.tracks.append(MidiTrack([
        Message("program_change", program=11),
        Message("note_on", note=60),
        Message("note_off", note=60, time=240),
    ]))
    path = tmp_path / "short.mid"
    midi.save(path)
    result = await _run_case(
        name="capture-regression", midi_path=path, output_names=("A",), plan=None,
        history_db=tmp_path / "history.db", targets=TimingTargets(),
    )
    summary = result.output_summaries["A"]
    assert summary.count == 2
    assert summary.scheduled_span_seconds == pytest.approx(0.25)
    # This tests capture identity, not CI-host timing performance: real sends
    # span the musical duration rather than adjacent startup resets.
    assert summary.drift_ms > -125


def test_exact_schedule_has_zero_jitter_and_drift() -> None:
    expected = [0.0, 0.25, 0.5, 1.0, 2.0]
    actual = [100.0 + value for value in expected]

    summary = summarize_timing(expected, actual)

    assert summary.count == len(expected)
    assert summary.p95_abs_interval_jitter_ms == pytest.approx(0.0, abs=1e-6)
    assert summary.p99_abs_interval_jitter_ms == pytest.approx(0.0, abs=1e-6)
    assert summary.max_abs_interval_jitter_ms == pytest.approx(0.0, abs=1e-6)
    assert summary.drift_ms == pytest.approx(0.0, abs=1e-6)


def test_timing_summary_removes_startup_offset_but_preserves_drift() -> None:
    expected = [0.0, 1.0, 2.0, 3.0]
    # Arbitrary 42-second startup offset plus 1 ms of accumulated drift per second.
    actual = [42.0, 43.001, 44.002, 45.003]

    summary = summarize_timing(expected, actual)

    assert summary.mean_interval_error_ms == pytest.approx(1.0, abs=1e-6)
    assert summary.max_abs_interval_jitter_ms == pytest.approx(1.0, abs=1e-6)
    assert summary.drift_ms == pytest.approx(3.0, abs=1e-6)


def test_two_output_skew_pairs_simultaneous_note_ons() -> None:
    a = [
        CapturedSend(0.0, 10.0000, "note_on", 0, 84),
        CapturedSend(1.0, 11.0004, "note_on", 0, 84),
        CapturedSend(2.0, 12.0008, "note_on", 0, 84),
    ]
    b = [
        CapturedSend(0.0, 10.0002, "note_on", 1, 84),
        CapturedSend(1.0, 11.0005, "note_on", 1, 84),
        CapturedSend(2.0, 12.0010, "note_on", 1, 84),
    ]

    summary = summarize_skew(a, b)

    assert summary.pair_count == 3
    assert summary.max_abs_skew_ms == pytest.approx(0.2, abs=1e-6)


def test_targets_report_scheduler_and_two_output_misses() -> None:
    bad = summarize_timing(
        [0.0, 1.0, 2.0],
        [10.0, 11.020, 12.040],
    )
    skew = summarize_skew(
        [CapturedSend(0.0, 10.000, "note_on", 0, 84)],
        [CapturedSend(0.0, 10.010, "note_on", 1, 84)],
    )

    failures = _failures({"A": bad}, skew, TimingTargets())

    assert any("p95 jitter" in failure for failure in failures)
    assert any("drift" in failure for failure in failures)
    assert any("two-output" in failure for failure in failures)


def test_timing_summary_rejects_mismatched_capture_counts() -> None:
    with pytest.raises(ValueError, match="counts differ"):
        summarize_timing([0.0, 1.0], [10.0])
