from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.testing.midi_fixtures import generate_suite

from .clock import SystemClock
from .engine import PlaybackEngine
from .history_adapter import SqliteHistoryRecorder
from .models import QueueItemSpec
from .outputs import MidiOutputRouter, VirtualMidiOutput
from .timeline import MidiTimeline


@dataclass(frozen=True, slots=True)
class TimingTargets:
    """Provisional software-scheduler targets, not MIDI-to-audio latency targets."""

    p95_interval_jitter_ms: float = 2.0
    p99_interval_jitter_ms: float = 5.0
    max_interval_jitter_ms: float = 10.0
    max_drift_ms: float = 5.0
    p95_two_output_skew_ms: float = 1.0
    max_two_output_skew_ms: float = 3.0


@dataclass(frozen=True, slots=True)
class ExpectedSend:
    scheduled_seconds: float
    message_type: str
    channel: int | None
    note: int | None


@dataclass(frozen=True, slots=True)
class CapturedSend:
    scheduled_seconds: float
    actual_seconds: float
    message_type: str
    channel: int | None
    note: int | None


@dataclass(frozen=True, slots=True)
class TimingSummary:
    count: int
    scheduled_span_seconds: float
    mean_interval_error_ms: float
    p95_abs_interval_jitter_ms: float
    p99_abs_interval_jitter_ms: float
    max_abs_interval_jitter_ms: float
    p95_abs_relative_error_ms: float
    max_abs_relative_error_ms: float
    drift_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SkewSummary:
    pair_count: int
    mean_signed_skew_ms: float
    p95_abs_skew_ms: float
    max_abs_skew_ms: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    name: str
    fixture: str
    logical_duration_seconds: float
    wall_duration_seconds: float
    output_summaries: dict[str, TimingSummary]
    two_output_skew: SkewSummary | None
    passed: bool
    failures: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "fixture": self.fixture,
            "logical_duration_seconds": round(self.logical_duration_seconds, 6),
            "wall_duration_seconds": round(self.wall_duration_seconds, 6),
            "output_summaries": {
                name: summary.to_dict() for name, summary in self.output_summaries.items()
            },
            "two_output_skew": (
                self.two_output_skew.to_dict() if self.two_output_skew is not None else None
            ),
            "passed": self.passed,
            "failures": list(self.failures),
        }


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    generated_at: str
    environment: dict[str, Any]
    targets: TimingTargets
    cases: tuple[BenchmarkCase, ...]

    @property
    def passed(self) -> bool:
        return all(case.passed for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "environment": self.environment,
            "targets": asdict(self.targets),
            "passed": self.passed,
            "cases": [case.to_dict() for case in self.cases],
        }


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (percentile / 100.0)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize_timing(expected_seconds: Sequence[float], actual_seconds: Sequence[float]) -> TimingSummary:
    """Summarize relative scheduler timing while removing arbitrary startup offset.

    The first send defines t=0 for both sequences. That intentionally excludes
    queue/startup latency and measures the musical clock after playback begins.
    """

    if len(expected_seconds) != len(actual_seconds):
        raise ValueError(
            f"expected/actual send counts differ: {len(expected_seconds)} != {len(actual_seconds)}"
        )
    if not expected_seconds:
        raise ValueError("at least one send is required")

    expected0 = float(expected_seconds[0])
    actual0 = float(actual_seconds[0])
    expected_relative = [float(value) - expected0 for value in expected_seconds]
    actual_relative = [float(value) - actual0 for value in actual_seconds]

    relative_errors_ms = [
        (actual - expected) * 1000.0
        for expected, actual in zip(expected_relative, actual_relative, strict=True)
    ]
    interval_errors_ms = [
        (
            (actual_relative[index] - actual_relative[index - 1])
            - (expected_relative[index] - expected_relative[index - 1])
        )
        * 1000.0
        for index in range(1, len(expected_relative))
    ]
    abs_interval = [abs(value) for value in interval_errors_ms]
    abs_relative = [abs(value) for value in relative_errors_ms]
    span = expected_relative[-1]
    drift = relative_errors_ms[-1]

    return TimingSummary(
        count=len(expected_relative),
        scheduled_span_seconds=round(span, 6),
        mean_interval_error_ms=round(
            statistics.fmean(interval_errors_ms) if interval_errors_ms else 0.0, 6
        ),
        p95_abs_interval_jitter_ms=round(_percentile(abs_interval, 95), 6),
        p99_abs_interval_jitter_ms=round(_percentile(abs_interval, 99), 6),
        max_abs_interval_jitter_ms=round(max(abs_interval, default=0.0), 6),
        p95_abs_relative_error_ms=round(_percentile(abs_relative, 95), 6),
        max_abs_relative_error_ms=round(max(abs_relative, default=0.0), 6),
        drift_ms=round(drift, 6),
    )


def summarize_skew(captures_a: Sequence[CapturedSend], captures_b: Sequence[CapturedSend]) -> SkewSummary:
    """Measure A/B send skew for simultaneous Note On events in sync-click.mid."""

    def note_ons(captures: Sequence[CapturedSend]) -> dict[float, float]:
        result: dict[float, float] = {}
        for capture in captures:
            if capture.message_type != "note_on":
                continue
            key = round(capture.scheduled_seconds, 9)
            result[key] = capture.actual_seconds
        return result

    a = note_ons(captures_a)
    b = note_ons(captures_b)
    common = sorted(set(a).intersection(b))
    if not common:
        raise ValueError("no simultaneous Note On pairs found")
    signed = [(a[key] - b[key]) * 1000.0 for key in common]
    absolute = [abs(value) for value in signed]
    return SkewSummary(
        pair_count=len(common),
        mean_signed_skew_ms=round(statistics.fmean(signed), 6),
        p95_abs_skew_ms=round(_percentile(absolute, 95), 6),
        max_abs_skew_ms=round(max(absolute), 6),
    )


def _expected_sends(
    timeline: MidiTimeline,
    router: MidiOutputRouter,
    plan: RoutingPlan | None,
) -> dict[str, list[ExpectedSend]]:
    expected = {name: [] for name in router.output_names}
    for event in timeline.events:
        routed = router.route_message(event.message, plan=plan)
        if routed is None:
            continue
        message = routed.message
        expected[routed.output.name].append(
            ExpectedSend(
                scheduled_seconds=event.at_seconds + routed.latency_seconds,
                message_type=message.type,
                channel=getattr(message, "channel", None),
                note=getattr(message, "note", None),
            )
        )
    return expected


def _capture(
    expected: Sequence[ExpectedSend],
    output: VirtualMidiOutput,
) -> list[CapturedSend]:
    # Completion invokes Panic, which intentionally adds cleanup messages after
    # the musical timeline. The expected musical count cleanly separates them.
    musical = output.sent[: len(expected)]
    if len(musical) != len(expected):
        raise RuntimeError(
            f"{output.name}: captured {len(musical)} musical sends, expected {len(expected)}"
        )
    return [
        CapturedSend(
            scheduled_seconds=expected_item.scheduled_seconds,
            actual_seconds=actual.at_seconds,
            message_type=expected_item.message_type,
            channel=expected_item.channel,
            note=expected_item.note,
        )
        for expected_item, actual in zip(expected, musical, strict=True)
    ]


def _failures(
    summaries: dict[str, TimingSummary],
    skew: SkewSummary | None,
    targets: TimingTargets,
) -> tuple[str, ...]:
    failures: list[str] = []
    for output, summary in summaries.items():
        if summary.p95_abs_interval_jitter_ms > targets.p95_interval_jitter_ms:
            failures.append(
                f"{output} p95 jitter {summary.p95_abs_interval_jitter_ms:.3f} ms "
                f"> {targets.p95_interval_jitter_ms:.3f} ms"
            )
        if summary.p99_abs_interval_jitter_ms > targets.p99_interval_jitter_ms:
            failures.append(
                f"{output} p99 jitter {summary.p99_abs_interval_jitter_ms:.3f} ms "
                f"> {targets.p99_interval_jitter_ms:.3f} ms"
            )
        if summary.max_abs_interval_jitter_ms > targets.max_interval_jitter_ms:
            failures.append(
                f"{output} max jitter {summary.max_abs_interval_jitter_ms:.3f} ms "
                f"> {targets.max_interval_jitter_ms:.3f} ms"
            )
        if abs(summary.drift_ms) > targets.max_drift_ms:
            failures.append(
                f"{output} drift {summary.drift_ms:.3f} ms exceeds "
                f"±{targets.max_drift_ms:.3f} ms"
            )
    if skew is not None:
        if skew.p95_abs_skew_ms > targets.p95_two_output_skew_ms:
            failures.append(
                f"two-output p95 skew {skew.p95_abs_skew_ms:.3f} ms "
                f"> {targets.p95_two_output_skew_ms:.3f} ms"
            )
        if skew.max_abs_skew_ms > targets.max_two_output_skew_ms:
            failures.append(
                f"two-output max skew {skew.max_abs_skew_ms:.3f} ms "
                f"> {targets.max_two_output_skew_ms:.3f} ms"
            )
    return tuple(failures)


async def _wait_for_stopped(engine: PlaybackEngine, timeout_seconds: float) -> None:
    queue = engine.events.subscribe()
    try:
        snapshot = await engine.playback_snapshot()
        if snapshot.state == "stopped":
            return
        while True:
            event = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
            if event.type == "state.playback" and event.payload.get("state") == "stopped":
                return
    finally:
        engine.events.unsubscribe(queue)


async def _run_case(
    *,
    name: str,
    midi_path: Path,
    output_names: Sequence[str],
    plan: RoutingPlan | None,
    history_db: Path,
    targets: TimingTargets,
) -> BenchmarkCase:
    clock = SystemClock()
    outputs = [VirtualMidiOutput(output_name, clock) for output_name in output_names]
    router = MidiOutputRouter(outputs, default_device=output_names[0])
    history = SqliteHistoryRecorder(history_db, clock)
    engine = PlaybackEngine(router=router, history=history, clock=clock)
    timeline = MidiTimeline.from_file(midi_path)
    expected = _expected_sends(timeline, router, plan)

    item = QueueItemSpec(
        asset_id=f"benchmark:{name}",
        title=f"Timing benchmark: {name}",
        duration_seconds=timeline.duration_seconds,
        midi_path=str(midi_path),
        routing_plan=plan,
    )

    wall_start = clock.now()
    try:
        await engine.set_queue([item])
        await engine.transport("play")
        await _wait_for_stopped(engine, max(10.0, timeline.duration_seconds + 10.0))
        wall_duration = clock.now() - wall_start

        captures: dict[str, list[CapturedSend]] = {}
        summaries: dict[str, TimingSummary] = {}
        for output in outputs:
            expected_output = expected[output.name]
            if not expected_output:
                continue
            captured = _capture(expected_output, output)
            captures[output.name] = captured
            summaries[output.name] = summarize_timing(
                [entry.scheduled_seconds for entry in captured],
                [entry.actual_seconds for entry in captured],
            )

        skew = None
        if len(output_names) == 2:
            skew = summarize_skew(captures[output_names[0]], captures[output_names[1]])
        failures = _failures(summaries, skew, targets)
        return BenchmarkCase(
            name=name,
            fixture=midi_path.name,
            logical_duration_seconds=timeline.duration_seconds,
            wall_duration_seconds=wall_duration,
            output_summaries=summaries,
            two_output_skew=skew,
            passed=not failures,
            failures=failures,
        )
    finally:
        await engine.close()


def _environment() -> dict[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "implementation": platform.python_implementation(),
    }


async def run_benchmark(
    *,
    long_run_minutes: int = 1,
    include_long_run: bool = True,
    targets: TimingTargets | None = None,
) -> BenchmarkReport:
    """Run the real SystemClock scheduler against virtual outputs in real time."""

    if not 1 <= long_run_minutes <= 24 * 60:
        raise ValueError("long_run_minutes must be between 1 and 1440")
    targets = targets or TimingTargets()

    with tempfile.TemporaryDirectory(prefix="openorchestrion-timing-") as temp:
        root = Path(temp)
        fixtures = root / "fixtures"
        generate_suite(fixtures, long_run_minutes=long_run_minutes)

        cases: list[BenchmarkCase] = []
        sync_plan = RoutingPlan(
            [
                MidiRoute(source_channel=0, destination_device="A"),
                MidiRoute(source_channel=1, destination_device="B"),
            ]
        )
        cases.append(
            await _run_case(
                name="sync-click-two-output",
                midi_path=fixtures / "sync-click.mid",
                output_names=("A", "B"),
                plan=sync_plan,
                history_db=root / "sync-history.db",
                targets=targets,
            )
        )
        if include_long_run:
            cases.append(
                await _run_case(
                    name=f"long-run-{long_run_minutes}m-one-output",
                    midi_path=fixtures / "long-run.mid",
                    output_names=("A",),
                    plan=None,
                    history_db=root / "long-history.db",
                    targets=targets,
                )
            )

        return BenchmarkReport(
            generated_at=datetime.now(UTC).isoformat(),
            environment={
                **_environment(),
                "event_loop": type(asyncio.get_running_loop()).__name__,
            },
            targets=targets,
            cases=tuple(cases),
        )


def _print_report(report: BenchmarkReport) -> None:
    print(f"OpenOrchestrion timing benchmark: {'PASS' if report.passed else 'FAIL'}")
    print(
        f"{report.environment['platform']} | Python {report.environment['python']} | "
        f"{report.environment['event_loop']}"
    )
    for case in report.cases:
        print(
            f"\n{case.name}: {'PASS' if case.passed else 'FAIL'} "
            f"({case.logical_duration_seconds:.2f}s musical / {case.wall_duration_seconds:.2f}s wall)"
        )
        for output, summary in case.output_summaries.items():
            print(
                f"  {output}: n={summary.count}, "
                f"p95 jitter={summary.p95_abs_interval_jitter_ms:.3f}ms, "
                f"p99={summary.p99_abs_interval_jitter_ms:.3f}ms, "
                f"max={summary.max_abs_interval_jitter_ms:.3f}ms, "
                f"drift={summary.drift_ms:+.3f}ms"
            )
        if case.two_output_skew is not None:
            skew = case.two_output_skew
            print(
                f"  A/B sync: n={skew.pair_count}, p95={skew.p95_abs_skew_ms:.3f}ms, "
                f"max={skew.max_abs_skew_ms:.3f}ms"
            )
        for failure in case.failures:
            print(f"  target miss: {failure}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Measure OpenOrchestrion real-time MIDI scheduler jitter and drift."
    )
    parser.add_argument(
        "--long-run-minutes",
        type=int,
        default=1,
        help="Logical long-run duration in minutes (default: 1; use 120+ on the reference Pi)",
    )
    parser.add_argument(
        "--sync-only",
        action="store_true",
        help="Run only the short two-output sync-click benchmark",
    )
    parser.add_argument("--json", dest="json_path", help="Write the full report to this JSON file")
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Exit non-zero when a provisional software timing target is missed",
    )
    args = parser.parse_args()

    report = asyncio.run(
        run_benchmark(
            long_run_minutes=args.long_run_minutes,
            include_long_run=not args.sync_only,
        )
    )
    _print_report(report)
    if args.json_path:
        destination = Path(args.json_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"\nreport: {destination}")
    if args.enforce and not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
