from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import validators
from referencing import Registry, Resource

from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.library.policy import audit_committed_music, count_committed_music
from openorchestrion.midi.analyzer import analyze_midi
from openorchestrion.models import PlaybackIntent
from openorchestrion.stations import build_station
from openorchestrion.testing.midi_fixtures import SUITE_RIGHTS, generate_suite

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "schemas"
DEVICE_PROFILES = ROOT / "device-profiles"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_native(value: Any) -> Any:
    """Round-trip through JSON so validators see only JSON-native container types."""
    return json.loads(json.dumps(value))


def _schema(name: str) -> dict[str, Any]:
    return _load_json(SCHEMAS / name)


def _registry() -> Registry:
    """Resolve every schema $ref from disk instead of over the network.

    midi-asset.schema.json refers to midi-analysis.schema.json relatively.
    Resolved against the declared $id that becomes a URL under
    openorchestrion.example — a reserved domain that cannot resolve anywhere —
    so jsonschema would attempt a network fetch and fail. Each schema is
    registered under both its $id and its bare filename so relative and
    absolute references both land locally.

    A local-first appliance must be able to validate its own schemas offline.
    """
    registry = Registry()
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        document = _load_json(path)
        resource = Resource.from_contents(document)
        registry = registry.with_resource(path.name, resource)
        identifier = document.get("$id")
        if identifier:
            registry = registry.with_resource(identifier, resource)
    return registry


def _validate(schema: dict[str, Any], instance: Any, label: str) -> None:
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)
    errors = sorted(
        validator_class(schema, registry=_registry()).iter_errors(_json_native(instance)),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        rendered = "\n".join(
            f"  - {'.'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        )
        raise SystemExit(f"{label} failed schema validation:\n{rendered}")


def validate_schema_documents() -> None:
    for path in sorted(SCHEMAS.glob("*.json")):
        schema = _load_json(path)
        validators.validator_for(schema).check_schema(schema)
        print(f"schema ok: {path.relative_to(ROOT)}")


def validate_device_profiles() -> None:
    schema = _schema("device-profile.schema.json")
    profiles = sorted(DEVICE_PROFILES.glob("*.json"))
    if not profiles:
        raise SystemExit("no device profiles found")
    for path in profiles:
        _validate(schema, _load_json(path), str(path.relative_to(ROOT)))
        print(f"device profile ok: {path.relative_to(ROOT)}")


def validate_generated_pipeline() -> None:
    analysis_schema = _schema("midi-analysis.schema.json")
    asset_schema = _schema("midi-asset.schema.json")
    intent_schema = _schema("playback-intent.schema.json")
    station_schema = _schema("station-queue.schema.json")

    with tempfile.TemporaryDirectory(prefix="openorchestrion-ci-") as temp:
        work = Path(temp)
        fixtures = work / "fixtures"
        library = work / "library"

        generated = generate_suite(fixtures, long_run_minutes=1)
        if len(generated) < 10:
            raise SystemExit(f"synthetic MIDI suite unexpectedly small: {len(generated)} fixtures")
        print(f"generated {len(generated)} synthetic MIDI fixtures")

        midi_files = sorted(fixtures.glob("*.mid"))
        if len(midi_files) != len(generated):
            raise SystemExit(
                f"fixture manifest/file mismatch: {len(generated)} declared, {len(midi_files)} files"
            )

        for midi_path in midi_files:
            analysis = analyze_midi(midi_path)
            _validate(
                analysis_schema,
                analysis.to_dict(),
                f"analysis for {midi_path.name}",
            )
        print(f"validated {len(midi_files)} generated MIDI analyses")

        # The generated suite is the one body of content this project can assert
        # rights over from first principles: it is the output of a generator in
        # this repository rather than anyone else's music. Importing it under a
        # real evidence record exercises the verified-open path end to end.
        report = import_paths([fixtures], library, rights=SUITE_RIGHTS)
        if report.failed:
            raise SystemExit(
                "import reported failures: "
                + ", ".join(f"{f.source} ({f.error_type}: {f.reason})" for f in report.failed)
            )
        imported = report.imported
        if len(imported) != len(midi_files):
            raise SystemExit(
                f"import count mismatch: expected {len(midi_files)}, imported {len(imported)}"
            )

        for result in imported:
            sidecar = Path(result.metadata_path)
            _validate(asset_schema, _load_json(sidecar), f"sidecar {sidecar.name}")
        print(f"validated {len(imported)} imported MIDI sidecars")

        rebuild = rebuild_catalog(library)
        if rebuild.indexed_assets != len(imported):
            raise SystemExit(
                f"catalog indexed {rebuild.indexed_assets} assets; expected {len(imported)}"
            )
        print(f"catalog rebuild ok: {rebuild.indexed_assets} assets")

        intent = PlaybackIntent()
        _validate(intent_schema, intent.model_dump(mode="json"), "PlaybackIntent")
        print("playback intent schema ok")

        queue = build_station(rebuild.db_path, intent, seed=7, max_tracks=5)
        if not queue.items:
            raise SystemExit("Smart Station produced an empty queue from the generated library")
        _validate(station_schema, queue.to_dict(), "Smart Station queue")
        print(f"station queue schema ok: {len(queue.items)} tracks")


def validate_committed_music() -> None:
    """No MIDI enters the repository without a rights record beside it."""
    music = ROOT / "music"
    offenders = audit_committed_music(music)
    if offenders:
        raise SystemExit(
            "committed MIDI without established redistribution rights:\n  "
            + "\n  ".join(offender.replace(f"{ROOT}/", "") for offender in offenders)
        )
    print(f"committed music ok: {count_committed_music(music)} MIDI file(s) with established rights")


def main() -> None:
    validate_schema_documents()
    validate_device_profiles()
    validate_generated_pipeline()
    validate_committed_music()
    print("repository contracts: ok")


if __name__ == "__main__":
    main()
