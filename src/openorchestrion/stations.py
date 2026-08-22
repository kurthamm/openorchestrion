from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from openorchestrion.models import PlaybackIntent

LEVELS = {"low": 1, "medium": 3, "high": 5}
QUALITY_POINTS = {"A": 5.0, "B": 4.0, "C": 2.5, "D": 1.0}


@dataclass(frozen=True, slots=True)
class StationConstraints:
    """Hard eligibility limits applied before station scoring."""

    rights_statuses: tuple[str, ...] = ()
    max_peak_simultaneous_notes: int | None = None
    note_receive_min: int | None = None
    note_receive_max: int | None = None
    allow_sysex: bool = True
    require_gm_compatible_structure: bool = False
    exclude_asset_ids: tuple[str, ...] = ()
    exclude_composition_ids: tuple[str, ...] = ()
    recent_asset_ids: tuple[str, ...] = ()
    recent_composition_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class StationWeights:
    """Explainable default scoring weights for Smart Stations."""

    genre: float = 12.0
    theme: float = 14.0
    mood: float = 8.0
    era: float = 6.0
    composer: float = 13.0
    artist: float = 9.0
    instrumentation: float = 9.0
    performance_type: float = 10.0
    familiarity: float = 8.0
    energy: float = 6.0
    favorite: float = 3.0
    quality: float = 1.0
    random_jitter: float = 0.75
    same_composer_penalty: float = 14.0
    composer_repeat_penalty: float = 1.5
    preferred_composer_repeat_penalty: float = 0.5
    energy_transition_penalty: float = 1.5
    overshoot_penalty_per_minute: float = 0.35


@dataclass(slots=True)
class Candidate:
    asset_id: str
    composition_id: str | None
    title: str | None
    composer: str | None
    artist: str | None
    era: str | None
    performance_type: str | None
    quality_grade: str | None
    familiarity: int | None
    energy: int | None
    favorite: bool
    duration_seconds: float
    rights_status: str
    peak_simultaneous_notes: int
    note_min: int | None
    note_max: int | None
    sysex_count: int
    gm_assessment: str | None
    midi_path: str
    tags: dict[str, set[str]] = field(default_factory=dict)
    base_score: float = 0.0
    tier: int = 0
    selected_for: list[str] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)
    tie_break: float = 0.0


@dataclass(frozen=True, slots=True)
class QueueItem:
    asset_id: str
    composition_id: str | None
    title: str
    composer: str | None
    duration_seconds: float
    midi_path: str
    score: float
    base_score: float
    match_tier: int
    selected_for: tuple[str, ...]
    score_breakdown: dict[str, float]
    sequence_adjustments: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["selected_for"] = list(self.selected_for)
        return value


@dataclass(frozen=True, slots=True)
class StationQueue:
    seed: int
    requested_duration_seconds: int | None
    total_duration_seconds: float
    candidate_assets: int
    candidate_compositions: int
    items: tuple[QueueItem, ...]
    relaxations: tuple[str, ...]
    diagnostics: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "requested_duration_seconds": self.requested_duration_seconds,
            "total_duration_seconds": round(self.total_duration_seconds, 3),
            "candidate_assets": self.candidate_assets,
            "candidate_compositions": self.candidate_compositions,
            "items": [item.to_dict() for item in self.items],
            "relaxations": list(self.relaxations),
            "diagnostics": list(self.diagnostics),
        }


def _connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _norm(value: str) -> str:
    return value.strip().casefold()


def _norm_values(values: Iterable[str]) -> set[str]:
    return {_norm(value) for value in values if str(value).strip()}


def _tie_break(seed: int, asset_id: str) -> float:
    digest = hashlib.sha256(f"{seed}:{asset_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / (2**64 - 1)


def _load_candidates(
    db_path: str | Path,
    constraints: StationConstraints,
    *,
    respect_recent: bool = True,
) -> list[Candidate]:
    clauses = ["1=1"]
    params: list[Any] = []
    if constraints.rights_statuses:
        placeholders = ",".join("?" for _ in constraints.rights_statuses)
        clauses.append(f"rights_status IN ({placeholders})")
        params.extend(constraints.rights_statuses)
    if constraints.max_peak_simultaneous_notes is not None:
        clauses.append("peak_simultaneous_notes <= ?")
        params.append(constraints.max_peak_simultaneous_notes)
    if constraints.note_receive_min is not None:
        clauses.append("(note_min IS NULL OR note_min >= ?)")
        params.append(constraints.note_receive_min)
    if constraints.note_receive_max is not None:
        clauses.append("(note_max IS NULL OR note_max <= ?)")
        params.append(constraints.note_receive_max)
    if not constraints.allow_sysex:
        clauses.append("sysex_count = 0")
    if constraints.require_gm_compatible_structure:
        clauses.append("gm_assessment = 'gm-compatible-structure'")

    sql = f"""
        SELECT asset_id, composition_id, title, composer, artist, era,
               performance_type, quality_grade, familiarity, energy, favorite,
               duration_seconds, rights_status, peak_simultaneous_notes,
               note_min, note_max, sysex_count, gm_assessment, midi_path,
               original_filename
        FROM assets
        WHERE {' AND '.join(clauses)}
        ORDER BY asset_id
    """
    with _connect(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
        tag_rows = conn.execute(
            "SELECT asset_id, kind, value FROM asset_tags ORDER BY asset_id, kind, value"
        ).fetchall()

    tags_by_asset: dict[str, dict[str, set[str]]] = {}
    for row in tag_rows:
        tags_by_asset.setdefault(row["asset_id"], {}).setdefault(row["kind"], set()).add(
            _norm(row["value"])
        )

    excluded_assets = set(constraints.exclude_asset_ids)
    excluded_compositions = set(constraints.exclude_composition_ids)
    if respect_recent:
        excluded_assets.update(constraints.recent_asset_ids)
        excluded_compositions.update(constraints.recent_composition_ids)

    result: list[Candidate] = []
    for row in rows:
        if row["asset_id"] in excluded_assets:
            continue
        if row["composition_id"] and row["composition_id"] in excluded_compositions:
            continue
        result.append(
            Candidate(
                asset_id=row["asset_id"],
                composition_id=row["composition_id"],
                title=row["title"] or row["original_filename"],
                composer=row["composer"],
                artist=row["artist"],
                era=row["era"],
                performance_type=row["performance_type"],
                quality_grade=row["quality_grade"],
                familiarity=row["familiarity"],
                energy=row["energy"],
                favorite=bool(row["favorite"]),
                duration_seconds=float(row["duration_seconds"]),
                rights_status=row["rights_status"],
                peak_simultaneous_notes=row["peak_simultaneous_notes"],
                note_min=row["note_min"],
                note_max=row["note_max"],
                sysex_count=row["sysex_count"],
                gm_assessment=row["gm_assessment"],
                midi_path=row["midi_path"],
                tags=tags_by_asset.get(row["asset_id"], {}),
            )
        )
    return result


def _category_match(candidate_values: set[str], requested: Sequence[str]) -> bool:
    wanted = _norm_values(requested)
    return bool(wanted and candidate_values.intersection(wanted))


def _tag_union(candidate: Candidate) -> set[str]:
    result: set[str] = set()
    for values in candidate.tags.values():
        result.update(values)
    return result


def _closeness_score(candidate: int | None, requested: str | None, weight: float) -> float:
    if candidate is None or requested is None:
        return 0.0
    target = LEVELS[requested]
    closeness = 1.0 - abs(candidate - target) / 4.0
    return max(0.0, closeness) * weight


def _score_candidate(
    candidate: Candidate,
    intent: PlaybackIntent,
    weights: StationWeights,
    seed: int,
) -> None:
    breakdown: dict[str, float] = {}
    reasons: list[str] = []
    identity_groups = 0
    identity_matches = 0

    def match_group(label: str, matched: bool, weight: float, reason: str) -> None:
        nonlocal identity_groups, identity_matches
        identity_groups += 1
        if matched:
            identity_matches += 1
            breakdown[label] = weight
            reasons.append(reason)

    if intent.genres:
        match_group(
            "genre",
            _category_match(candidate.tags.get("genre", set()), intent.genres),
            weights.genre,
            "genre match",
        )
    if intent.themes:
        match_group(
            "theme",
            _category_match(candidate.tags.get("theme", set()), intent.themes),
            weights.theme,
            "theme match",
        )
    if intent.moods:
        match_group(
            "mood",
            _category_match(candidate.tags.get("mood", set()), intent.moods),
            weights.mood,
            "mood match",
        )
    if intent.eras:
        match_group(
            "era",
            candidate.era is not None and _norm(candidate.era) in _norm_values(intent.eras),
            weights.era,
            "era match",
        )
    # Composer/artist are weighted preferences rather than match-tier gates. This allows
    # requests such as "ragtime, mostly Joplin" to retain some composer diversity.
    if (
        intent.composers
        and candidate.composer is not None
        and _norm(candidate.composer) in _norm_values(intent.composers)
    ):
        breakdown["composer"] = weights.composer
        reasons.append("preferred composer")
    if (
        intent.artists
        and candidate.artist is not None
        and _norm(candidate.artist) in _norm_values(intent.artists)
    ):
        breakdown["artist"] = weights.artist
        reasons.append("preferred artist")
    if intent.instrumentation:
        match_group(
            "instrumentation",
            _category_match(
                candidate.tags.get("instrumentation", set()), intent.instrumentation
            ),
            weights.instrumentation,
            "instrumentation match",
        )
    if intent.performance_types:
        wanted_types = {_norm(str(value)) for value in intent.performance_types}
        match_group(
            "performance_type",
            candidate.performance_type is not None
            and _norm(candidate.performance_type) in wanted_types,
            weights.performance_type,
            "performance type match",
        )

    familiarity = _closeness_score(candidate.familiarity, intent.familiarity, weights.familiarity)
    if familiarity:
        breakdown["familiarity"] = familiarity
        reasons.append(f"familiarity {candidate.familiarity}/5")
    energy = _closeness_score(candidate.energy, intent.energy, weights.energy)
    if energy:
        breakdown["energy"] = energy
        reasons.append(f"energy {candidate.energy}/5")
    if candidate.favorite:
        breakdown["favorite"] = weights.favorite
        reasons.append("favorite")
    quality = QUALITY_POINTS.get((candidate.quality_grade or "").upper(), 0.0) * weights.quality
    if quality:
        breakdown["quality"] = quality
        reasons.append(f"quality {candidate.quality_grade}")

    candidate.tie_break = _tie_break(seed, candidate.asset_id)
    breakdown["seeded_jitter"] = candidate.tie_break * weights.random_jitter
    candidate.base_score = sum(breakdown.values())
    candidate.score_breakdown = breakdown
    candidate.selected_for = reasons
    if identity_groups == 0 or identity_matches == identity_groups:
        candidate.tier = 0
    elif identity_matches > 0:
        candidate.tier = 1
    else:
        candidate.tier = 2


def _passes_hard_tags(candidate: Candidate, intent: PlaybackIntent) -> bool:
    all_tags = _tag_union(candidate)
    include = _norm_values(intent.include_tags)
    exclude = _norm_values(intent.exclude_tags)
    return include.issubset(all_tags) and not bool(exclude.intersection(all_tags))


def _best_asset_per_composition(candidates: Sequence[Candidate]) -> list[Candidate]:
    groups: dict[str, list[Candidate]] = {}
    for candidate in candidates:
        key = candidate.composition_id or f"asset:{candidate.asset_id}"
        groups.setdefault(key, []).append(candidate)

    result: list[Candidate] = []
    for values in groups.values():
        result.append(
            min(
                values,
                key=lambda item: (
                    item.tier,
                    -item.base_score,
                    -QUALITY_POINTS.get((item.quality_grade or "").upper(), 0.0),
                    item.tie_break,
                    item.asset_id,
                ),
            )
        )
    return result


def _effective_score(
    candidate: Candidate,
    *,
    previous: Candidate | None,
    composer_counts: dict[str, int],
    preferred_composers: set[str],
    remaining_seconds: float | None,
    weights: StationWeights,
) -> tuple[float, dict[str, float]]:
    adjustments: dict[str, float] = {}
    composer_key = _norm(candidate.composer) if candidate.composer else None
    if (
        previous
        and candidate.composer
        and previous.composer
        and _norm(candidate.composer) == _norm(previous.composer)
    ):
        adjustments["same_composer"] = -weights.same_composer_penalty
    if composer_key:
        count = composer_counts.get(composer_key, 0)
        if count:
            penalty = (
                weights.preferred_composer_repeat_penalty
                if composer_key in preferred_composers
                else weights.composer_repeat_penalty
            )
            adjustments["composer_representation"] = -(count * penalty)
    if previous and candidate.energy is not None and previous.energy is not None:
        delta = abs(candidate.energy - previous.energy)
        if delta > 1:
            adjustments["energy_transition"] = -(
                (delta - 1) * weights.energy_transition_penalty
            )
    if remaining_seconds is not None and candidate.duration_seconds > remaining_seconds:
        overshoot_minutes = (
            candidate.duration_seconds - max(0.0, remaining_seconds)
        ) / 60.0
        adjustments["duration_overshoot"] = -(
            overshoot_minutes * weights.overshoot_penalty_per_minute
        )
    return candidate.base_score + sum(adjustments.values()), adjustments


def build_station(
    db_path: str | Path,
    intent: PlaybackIntent,
    *,
    constraints: StationConstraints | None = None,
    weights: StationWeights | None = None,
    seed: int = 0,
    max_tracks: int = 25,
) -> StationQueue:
    """Build an explainable deterministic queue from a validated PlaybackIntent."""

    if not 1 <= max_tracks <= 1000:
        raise ValueError("max_tracks must be between 1 and 1000")
    constraints = constraints or StationConstraints()
    weights = weights or StationWeights()
    diagnostics: list[str] = []
    if intent.tempo_preference and intent.tempo_preference != "mixed":
        diagnostics.append(
            "tempo_preference is not yet scored because catalog tempo summary is not indexed"
        )
    if intent.device_preferences or intent.routing_preferences:
        diagnostics.append(
            "device/routing preferences are carried downstream; use StationConstraints "
            "for current eligibility limits"
        )

    raw = _load_candidates(
        db_path,
        constraints,
        respect_recent=intent.avoid_recent_repeats,
    )
    for candidate in raw:
        _score_candidate(candidate, intent, weights, seed)
    eligible = [candidate for candidate in raw if _passes_hard_tags(candidate, intent)]
    best = _best_asset_per_composition(eligible)

    requested_seconds = intent.duration_minutes * 60 if intent.duration_minutes else None
    selected: list[QueueItem] = []
    selected_candidates: list[Candidate] = []
    total = 0.0
    composer_counts: dict[str, int] = {}
    preferred_composers = _norm_values(intent.composers)
    relaxations: list[str] = []
    remaining_candidates = list(best)
    current_tier = 0

    while remaining_candidates and len(selected) < max_tracks:
        if requested_seconds is not None and total >= requested_seconds:
            break
        available_tier = min(candidate.tier for candidate in remaining_candidates)
        if available_tier > current_tier:
            if available_tier == 1:
                relaxations.append("relaxed exact metadata matching to partial matches")
            elif available_tier == 2:
                relaxations.append(
                    "relaxed requested metadata preferences to remaining eligible library"
                )
            current_tier = available_tier

        pool = [candidate for candidate in remaining_candidates if candidate.tier == available_tier]
        previous = selected_candidates[-1] if selected_candidates else None
        remaining_seconds = None if requested_seconds is None else requested_seconds - total
        scored: list[tuple[float, float, Candidate, dict[str, float]]] = []
        for candidate in pool:
            effective, adjustments = _effective_score(
                candidate,
                previous=previous,
                composer_counts=composer_counts,
                preferred_composers=preferred_composers,
                remaining_seconds=remaining_seconds,
                weights=weights,
            )
            scored.append((effective, candidate.tie_break, candidate, adjustments))

        effective, _, chosen, adjustments = max(
            scored,
            key=lambda item: (item[0], item[1], item[2].asset_id),
        )
        selected.append(
            QueueItem(
                asset_id=chosen.asset_id,
                composition_id=chosen.composition_id,
                title=chosen.title or chosen.asset_id,
                composer=chosen.composer,
                duration_seconds=chosen.duration_seconds,
                midi_path=chosen.midi_path,
                score=round(effective, 6),
                base_score=round(chosen.base_score, 6),
                match_tier=chosen.tier,
                selected_for=tuple(chosen.selected_for),
                score_breakdown={
                    key: round(value, 6) for key, value in chosen.score_breakdown.items()
                },
                sequence_adjustments={
                    key: round(value, 6) for key, value in adjustments.items()
                },
            )
        )
        selected_candidates.append(chosen)
        total += chosen.duration_seconds
        if chosen.composer:
            key = _norm(chosen.composer)
            composer_counts[key] = composer_counts.get(key, 0) + 1
        remaining_candidates.remove(chosen)

    if requested_seconds is not None and total < requested_seconds:
        relaxations.append(
            "library exhausted before requested duration "
            f"({total / 60:.1f} of {intent.duration_minutes} minutes)"
        )

    return StationQueue(
        seed=seed,
        requested_duration_seconds=requested_seconds,
        total_duration_seconds=round(total, 3),
        candidate_assets=len(eligible),
        candidate_compositions=len(best),
        items=tuple(selected),
        relaxations=tuple(dict.fromkeys(relaxations)),
        diagnostics=tuple(diagnostics),
    )


def _intent_from_args(args: argparse.Namespace) -> PlaybackIntent:
    if args.intent_json:
        return PlaybackIntent.model_validate_json(
            Path(args.intent_json).read_text(encoding="utf-8")
        )
    return PlaybackIntent(
        duration_minutes=args.duration_minutes,
        genres=args.genre,
        moods=args.mood,
        themes=args.theme,
        eras=args.era,
        composers=args.composer,
        artists=args.artist,
        instrumentation=args.instrumentation,
        performance_types=args.performance_type,
        familiarity=args.familiarity,
        energy=args.energy,
        include_tags=args.include_tag,
        exclude_tags=args.exclude_tag,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a deterministic OpenOrchestrion Smart Station queue."
    )
    parser.add_argument("db", nargs="?", default="var/library/catalog.db")
    parser.add_argument("--intent-json", help="PlaybackIntent JSON file; overrides intent flags")
    parser.add_argument("--duration-minutes", type=int)
    parser.add_argument("--genre", action="append", default=[])
    parser.add_argument("--mood", action="append", default=[])
    parser.add_argument("--theme", action="append", default=[])
    parser.add_argument("--era", action="append", default=[])
    parser.add_argument("--composer", action="append", default=[])
    parser.add_argument("--artist", action="append", default=[])
    parser.add_argument("--instrumentation", action="append", default=[])
    parser.add_argument("--performance-type", action="append", default=[])
    parser.add_argument("--familiarity", choices=("low", "medium", "high"))
    parser.add_argument("--energy", choices=("low", "medium", "high"))
    parser.add_argument("--include-tag", action="append", default=[])
    parser.add_argument("--exclude-tag", action="append", default=[])
    parser.add_argument("--rights-status", action="append", default=[])
    parser.add_argument("--max-peak-notes", type=int)
    parser.add_argument("--note-receive-min", type=int)
    parser.add_argument("--note-receive-max", type=int)
    parser.add_argument("--disallow-sysex", action="store_true")
    parser.add_argument("--require-gm-compatible", action="store_true")
    parser.add_argument("--recent-asset", action="append", default=[])
    parser.add_argument("--recent-composition", action="append", default=[])
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--max-tracks", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    intent = _intent_from_args(args)
    constraints = StationConstraints(
        rights_statuses=tuple(args.rights_status),
        max_peak_simultaneous_notes=args.max_peak_notes,
        note_receive_min=args.note_receive_min,
        note_receive_max=args.note_receive_max,
        allow_sysex=not args.disallow_sysex,
        require_gm_compatible_structure=args.require_gm_compatible,
        recent_asset_ids=tuple(args.recent_asset),
        recent_composition_ids=tuple(args.recent_composition),
    )
    queue = build_station(
        args.db,
        intent,
        constraints=constraints,
        seed=args.seed,
        max_tracks=args.max_tracks,
    )
    if args.json:
        print(json.dumps(queue.to_dict(), indent=2, sort_keys=True))
        return

    print(
        f"Smart Station: {len(queue.items)} tracks, "
        f"{queue.total_duration_seconds / 60:.1f} minutes, seed={queue.seed}"
    )
    for index, item in enumerate(queue.items, start=1):
        reason = ", ".join(item.selected_for) or "eligible library candidate"
        print(
            f"{index:>2}. {item.title} | {item.composer or 'Unknown'} | "
            f"{item.duration_seconds / 60:.1f}m | score {item.score:.2f} | {reason}"
        )
    for relaxation in queue.relaxations:
        print(f"relaxed: {relaxation}")
    for diagnostic in queue.diagnostics:
        print(f"note: {diagnostic}")


if __name__ == "__main__":
    main()
