import hashlib
import io
import json

import pytest
from mido import Message, MidiFile, MidiTrack

from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.curation import admitted_ids
from openorchestrion.library.importer import import_paths
from openorchestrion.library.quality import VERSION
from openorchestrion.library.quality_transaction import apply, restore


def prepare(tmp_path):
    root = tmp_path / "library"
    for index in range(2):
        file = MidiFile()
        file.tracks = [
            MidiTrack(
                [
                    Message("note_on", note=60 + index),
                    Message("note_off", note=60 + index, time=480),
                ]
            )
        ]
        raw = io.BytesIO()
        file.save(file=raw)
        source = tmp_path / f"{index}.mid"
        source.write_bytes(raw.getvalue())
        assert not import_paths([source], root).failed
    paths = sorted((root / "assets").glob("*.json"))
    old = root / "archive" / "prior" / "assets"
    old.mkdir(parents=True)
    for suffix in (".mid", ".json"):
        paths[1].with_suffix(suffix).replace(old / paths[1].with_suffix(suffix).name)
    manifest = {
        "policy_version": "household-listening-v1",
        "run": "prior",
        "asset_ids": ["sha256:" + paths[0].stem],
    }
    (root / "listening-admission.json").write_text(json.dumps(manifest))
    rebuild_catalog(root)
    entries = []
    for path, status in ((paths[0], "unresolved"), (old / paths[1].name, "qualified")):
        entries.append(
            {
                "asset_id": "sha256:" + path.stem,
                "sidecar_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "original_location": path.relative_to(root).as_posix(),
                "status": status,
                "reasons": [] if status == "qualified" else ["completeness_unresolved"],
                "evidence": [{"completeness": "complete"}] if status == "qualified" else [],
                "display": {"status": "qualified"},
            }
        )
    return root, {"policy_version": VERSION, "entries": entries}, manifest


def test_publish_recovers_prior_exclusion_and_restore_returns_both_locations(tmp_path):
    root, plan, manifest = prepare(tmp_path)
    before = {
        e["original_location"]: (root / e["original_location"]).read_bytes()
        for e in plan["entries"]
    }
    run = apply(root, plan)
    assert admitted_ids(root) == {plan["entries"][1]["asset_id"]}
    assert (root / "quality.sqlite3").exists()
    restore(root, run)
    assert json.loads((root / "listening-admission.json").read_bytes()) == manifest
    assert not (root / "quality.sqlite3").exists()
    for relative, raw in before.items():
        assert (root / relative).read_bytes() == raw


def test_publication_failure_rolls_back_all_moves_and_policy(tmp_path, monkeypatch):
    root, plan, manifest = prepare(tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("injected catalog failure")

    monkeypatch.setattr("openorchestrion.library.catalog.rebuild_catalog", fail)
    with pytest.raises(RuntimeError, match="injected"):
        apply(root, plan)
    assert json.loads((root / "listening-admission.json").read_bytes()) == manifest
    assert all((root / e["original_location"]).exists() for e in plan["entries"])
    assert not (root / ".curation-lock").exists()


def test_stale_input_is_rejected_before_moving_files(tmp_path):
    root, plan, _ = prepare(tmp_path)
    path = root / plan["entries"][0]["original_location"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="source changed"):
        apply(root, plan)
    assert all((root / e["original_location"]).exists() for e in plan["entries"])


def test_active_backup_restores_admission_and_quality_evidence(tmp_path):
    from openorchestrion.backup import create_backup, restore_backup
    from openorchestrion.library.qualification import qualification

    root, plan, _ = prepare(tmp_path)
    apply(root, plan)
    archive = tmp_path.parent / (tmp_path.name + ".zip")
    recovered = tmp_path.parent / (tmp_path.name + "-restored")
    create_backup(tmp_path, archive)
    restore_backup(archive, recovered)
    asset = plan["entries"][1]["asset_id"]
    assert admitted_ids(recovered / "library") == {asset}
    assert qualification(recovered / "library" / "catalog.db", asset) == {"status": "qualified"}
    assert not (recovered / "library" / "archive").exists()


def test_destination_collision_does_not_move_unrelated_midi(tmp_path):
    root, plan, manifest = prepare(tmp_path)
    path = root / "assets" / (plan["entries"][1]["asset_id"][7:] + ".mid")
    path.write_bytes(b"unrelated orphan")
    with pytest.raises(ValueError, match="collision"):
        apply(root, plan)
    assert path.read_bytes() == b"unrelated orphan"
    assert all((root / e["original_location"]).exists() for e in plan["entries"])
    assert json.loads((root / "listening-admission.json").read_bytes()) == manifest
