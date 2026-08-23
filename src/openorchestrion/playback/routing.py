from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from openorchestrion.midi.router import MidiRoute, RoutingPlan
from openorchestrion.models import DeviceProfile, PerformanceType

from .timeline import MidiTimeline


class RoutingPlanError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RoutingEndpoint:
    """One playback output plus the capabilities used by the routing planner."""

    output_name: str
    profile: DeviceProfile | None = None

    @property
    def capacity(self) -> int:
        return self.profile.max_polyphony if self.profile and self.profile.max_polyphony else 128

    @property
    def latency_offset_ms(self) -> float:
        return self.profile.latency_offset_ms if self.profile else 0.0

    @property
    def preferred_families(self) -> frozenset[str]:
        if not self.profile:
            return frozenset()
        return frozenset(_norm(value) for value in self.profile.preferred_instrument_families)

    def matches_preference(self, token: str) -> bool:
        wanted = _norm(token)
        candidates = {_norm(self.output_name)}
        if self.profile:
            candidates.update(
                {
                    _norm(self.profile.id),
                    _norm(self.profile.model),
                    _norm(self.profile.manufacturer),
                }
            )
        return wanted in candidates


@dataclass(frozen=True, slots=True)
class PartDemand:
    track_index: int | None
    channel: int
    family: str
    peak_keyed_notes: int
    note_count: int
    percussion: bool

    @property
    def key(self) -> tuple[int | None, int]:
        return self.track_index, self.channel


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    plan: RoutingPlan
    parts: tuple[PartDemand, ...]
    estimated_peak_load: dict[str, int]
    diagnostics: tuple[str, ...]


def _norm(value: str) -> str:
    return value.strip().casefold().replace("_", " ").replace("-", " ")


def _gm_family(program: int) -> str:
    if not 0 <= program <= 127:
        return "unknown"
    families = (
        "piano",
        "chromatic percussion",
        "organ",
        "guitar",
        "bass",
        "strings",
        "ensemble",
        "brass",
        "reed",
        "pipe",
        "synth lead",
        "synth pad",
        "synth effects",
        "ethnic",
        "percussion",
        "sound effects",
    )
    return families[program // 8]


def analyze_part_demands(timeline: MidiTimeline) -> tuple[PartDemand, ...]:
    """Measure track/channel parts without depending on catalog analyzer state.

    This intentionally counts currently keyed notes, not sustain-held voices. It
    is a routing load estimate, not the durable analyzer's compatibility fact.
    """

    programs: dict[tuple[int | None, int], int] = defaultdict(int)
    family_counts: dict[tuple[int | None, int], Counter[str]] = defaultdict(Counter)
    active: dict[tuple[int | None, int], set[int]] = defaultdict(set)
    peak: dict[tuple[int | None, int], int] = defaultdict(int)
    note_counts: Counter[tuple[int | None, int]] = Counter()

    for event in timeline.events:
        message = event.message
        if not hasattr(message, "channel"):
            continue
        channel = int(message.channel)
        key = (event.track_index, channel)
        if message.type == "program_change":
            programs[key] = int(message.program)
            continue
        if message.type == "note_on" and message.velocity > 0:
            family = "percussion" if channel == 9 else _gm_family(programs[key])
            family_counts[key][family] += 1
            note_counts[key] += 1
            active[key].add(int(message.note))
            peak[key] = max(peak[key], len(active[key]))
        elif message.type == "note_off" or (
            message.type == "note_on" and message.velocity == 0
        ):
            active[key].discard(int(message.note))

    parts: list[PartDemand] = []
    for key in sorted(note_counts, key=lambda value: ((value[0] or -1), value[1])):
        track_index, channel = key
        counts = family_counts[key]
        family = counts.most_common(1)[0][0] if counts else ("percussion" if channel == 9 else "piano")
        parts.append(
            PartDemand(
                track_index=track_index,
                channel=channel,
                family=family,
                peak_keyed_notes=max(1, peak[key]),
                note_count=note_counts[key],
                percussion=channel == 9,
            )
        )
    return tuple(parts)


def _ordered_endpoints(
    endpoints: Sequence[RoutingEndpoint],
    device_preferences: Iterable[str],
) -> list[RoutingEndpoint]:
    remaining = list(endpoints)
    ordered: list[RoutingEndpoint] = []
    for token in device_preferences:
        match = next((endpoint for endpoint in remaining if endpoint.matches_preference(token)), None)
        if match is not None:
            ordered.append(match)
            remaining.remove(match)
    ordered.extend(sorted(remaining, key=lambda endpoint: endpoint.output_name.casefold()))
    return ordered


def _latency_delays(endpoints: Sequence[RoutingEndpoint]) -> dict[str, float]:
    if not endpoints:
        return {}
    raw = {endpoint.output_name: endpoint.latency_offset_ms for endpoint in endpoints}
    baseline = min(raw.values())
    # Preserve relative calibration while ensuring the scheduler never needs a
    # negative send time. A negative configured offset simply moves every other
    # destination later by the same amount.
    return {name: round(value - baseline, 6) for name, value in raw.items()}


def _role_endpoint(
    endpoints: Sequence[RoutingEndpoint],
    routing_preferences: Mapping[str, str],
    role_names: Sequence[str],
    *,
    excluded: set[str] | None = None,
) -> RoutingEndpoint | None:
    excluded = excluded or set()
    for role in role_names:
        token = routing_preferences.get(role)
        if not token:
            continue
        match = next(
            (
                endpoint
                for endpoint in endpoints
                if endpoint.output_name not in excluded and endpoint.matches_preference(token)
            ),
            None,
        )
        if match is not None:
            return match
    return next((endpoint for endpoint in endpoints if endpoint.output_name not in excluded), None)


def _family_penalty(endpoint: RoutingEndpoint, family: str) -> float:
    preferred = endpoint.preferred_families
    if not preferred:
        return 0.25
    wanted = _norm(family)
    return 0.0 if wanted in preferred else 1.0


def _assign_balanced(
    part: PartDemand,
    endpoints: Sequence[RoutingEndpoint],
    loads: dict[str, int],
) -> RoutingEndpoint:
    if not endpoints:
        raise RoutingPlanError("no routing endpoints are available")

    def score(endpoint: RoutingEndpoint) -> tuple[float, float, str]:
        projected = loads[endpoint.output_name] + part.peak_keyed_notes
        ratio = projected / max(1, endpoint.capacity)
        return _family_penalty(endpoint, part.family), ratio, endpoint.output_name.casefold()

    return min(endpoints, key=score)


def plan_routing(
    timeline: MidiTimeline,
    endpoints: Sequence[RoutingEndpoint],
    *,
    performance_type: PerformanceType | str | None = None,
    device_preferences: Iterable[str] = (),
    routing_preferences: Mapping[str, str] | None = None,
) -> RoutingDecision:
    """Build a deterministic routing plan from timeline demand and device capability."""

    if not endpoints:
        raise RoutingPlanError("no MIDI outputs are available")
    routing_preferences = routing_preferences or {}
    ordered = _ordered_endpoints(endpoints, device_preferences)
    parts = analyze_part_demands(timeline)
    delays = _latency_delays(ordered)
    loads = {endpoint.output_name: 0 for endpoint in ordered}
    diagnostics: list[str] = []
    routes: list[MidiRoute] = []

    if len(ordered) == 1:
        diagnostics.append("only one output is available; all parts remain on that device")

    kind = PerformanceType(performance_type) if performance_type else None
    paired_piano = kind in {
        PerformanceType.TWO_PIANO,
        PerformanceType.PIANO_DUET,
        PerformanceType.DUELING_PIANO,
    }

    piano_a: RoutingEndpoint | None = None
    piano_b: RoutingEndpoint | None = None
    if paired_piano and len(ordered) >= 2:
        piano_a = _role_endpoint(
            ordered,
            routing_preferences,
            ("piano_a", "piano_1", "primo"),
        )
        piano_b = _role_endpoint(
            ordered,
            routing_preferences,
            ("piano_b", "piano_2", "secondo"),
            excluded={piano_a.output_name} if piano_a else set(),
        )
        if piano_a is None or piano_b is None:
            raise RoutingPlanError("two-piano routing requires two distinct outputs")

    paired_parts = [part for part in parts if part.family == "piano"]
    paired_parts.sort(key=lambda part: ((part.track_index or -1), part.channel))
    paired_assignment: dict[tuple[int | None, int], RoutingEndpoint] = {}
    if piano_a and piano_b:
        if len(paired_parts) < 2:
            diagnostics.append(
                f"{kind.value} requested but fewer than two separable piano parts were detected"
            )
        for index, part in enumerate(paired_parts):
            paired_assignment[part.key] = piano_a if index % 2 == 0 else piano_b

    for part in parts:
        endpoint = paired_assignment.get(part.key)
        if endpoint is None:
            if kind == PerformanceType.SOLO_PIANO:
                endpoint = ordered[0]
            elif kind in {
                PerformanceType.MULTI_INSTRUMENT,
                PerformanceType.DISTRIBUTED,
            }:
                endpoint = _assign_balanced(part, ordered, loads)
            elif paired_piano:
                # Non-piano accompaniment in a duet/dueling arrangement is load
                # balanced after the principal piano identities are fixed.
                endpoint = _assign_balanced(part, ordered, loads)
            else:
                preferred = [
                    candidate
                    for candidate in ordered
                    if _family_penalty(candidate, part.family) == 0.0
                ]
                endpoint = _assign_balanced(part, preferred, loads) if preferred else ordered[0]

        loads[endpoint.output_name] += part.peak_keyed_notes
        routes.append(
            MidiRoute(
                source_channel=part.channel,
                source_track=part.track_index,
                destination_device=endpoint.output_name,
                latency_offset_ms=delays[endpoint.output_name],
            )
        )

    if not parts:
        diagnostics.append("timeline contains no note-bearing channel parts; default output will be used")

    for endpoint in ordered:
        if endpoint.profile is None:
            diagnostics.append(
                f"{endpoint.output_name}: no device profile attached; generic routing capability assumed"
            )
        elif loads[endpoint.output_name] > endpoint.capacity:
            diagnostics.append(
                f"{endpoint.output_name}: estimated keyed-note load {loads[endpoint.output_name]} "
                f"exceeds nominal polyphony {endpoint.capacity}"
            )

    return RoutingDecision(
        plan=RoutingPlan(routes=routes, failure_policy="stop", diagnostics=list(diagnostics)),
        parts=parts,
        estimated_peak_load=dict(loads),
        diagnostics=tuple(diagnostics),
    )
