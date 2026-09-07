from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

import mido
import pytest

from openorchestrion.library.catalog import rebuild_catalog, reindex_asset, search_catalog
from openorchestrion.library.curation import POLICY_VERSION, inspect_asset, inspect_asset_reference, make_plan
from openorchestrion.library.curation_transaction import apply_plan, restore_run
from openorchestrion.midi.analyzer import analyze_midi


def asset(root: Path, *, flat=False, program=0, tail=0, name="piece") -> Path:
    (root / "assets").mkdir(parents=True, exist_ok=True)
    source = root / "input.mid"
    midi = mido.MidiFile()
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name=name))
    track.append(mido.Message("program_change", program=program))
    for i in range(100):
        track.append(mido.Message("note_on", note=60 + i % 12, velocity=90 if flat else 60 + i % 30, time=0))
        track.append(mido.Message("note_off", note=60 + i % 12, time=480))
    track.append(mido.MetaMessage("end_of_track", time=tail))
    midi.save(source)
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    dest = root / "assets" / f"{sha}.mid"
    source.replace(dest)
    analysis = analyze_midi(dest).to_dict()
    document = {"schema_version": 1, "asset_id": f"sha256:{sha}",
                "file": {"sha256": sha, "original_filename": name + ".mid", "stored_filename": dest.name, "size_bytes": dest.stat().st_size},
                "provenance": {"rights_status": "personal", "imported_at": "2026-09-07T00:00:00Z"},
                "deterministic_analysis": analysis, "descriptive_metadata": {"title": name}, "ai_enrichment": []}
    dest.with_suffix(".json").write_text(json.dumps(document))
    return dest.with_suffix(".json")


@pytest.mark.parametrize("flat,program,tail,reason", [
    (False, 0, 0, None), (True, 0, 0, "mechanical_piano_performance"),
    (True, 19, 0, None), (False, 0, 480000, "extreme_event_gap"),
])
def test_admission_and_reference_scanner(tmp_path, flat, program, tail, reason):
    path = asset(tmp_path, flat=flat, program=program, tail=tail)
    result = inspect_asset(str(path))
    assert result == inspect_asset_reference(str(path))
    assert (reason in result["reasons"]) if reason else not result["reasons"]


def plan_for(root):
    entries = [inspect_asset(str(p)) for p in sorted((root / "assets").glob("*.json"))]
    return {"policy_version": POLICY_VERSION, "library_root": str(root), "entries": entries}


def test_reversible_archive_and_future_import_gate(tmp_path):
    keep = asset(tmp_path, name="expressive")
    rejected = asset(tmp_path, flat=True, name="flat")
    rebuild_catalog(tmp_path)
    plan = plan_for(tmp_path)
    run = apply_plan(tmp_path, plan, run_name="test-run")
    assert keep.exists() and not rejected.exists()
    assert (run / "assets" / rejected.name).exists()
    assert len(search_catalog(tmp_path / "catalog.db")) == 1
    restore_run(tmp_path, run)
    assert keep.exists() and rejected.exists()
    assert len(search_catalog(tmp_path / "catalog.db")) == 2
    apply_plan(tmp_path, plan, run_name="test-run-2")
    incoming = asset(tmp_path, program=19, name="new unassessed file")
    assert rebuild_catalog(tmp_path).indexed_assets == 1
    assert not reindex_asset(tmp_path / "catalog.db", tmp_path, "sha256:" + incoming.stem)
    assert len(search_catalog(tmp_path / "catalog.db")) == 1


def test_stale_plan_changes_nothing(tmp_path):
    path = asset(tmp_path, flat=True)
    rebuild_catalog(tmp_path)
    plan = plan_for(tmp_path)
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="changed after scan"):
        apply_plan(tmp_path, plan)
    assert path.exists() and not (tmp_path / "archive").exists()


def test_failure_between_pair_moves_restores_catalog_and_originals(tmp_path, monkeypatch):
    import openorchestrion.library.curation_transaction as transaction
    path = asset(tmp_path, flat=True)
    asset(tmp_path, name="keep")
    rebuild_catalog(tmp_path)
    with sqlite3.connect(tmp_path / "catalog.db") as conn:
        before = list(conn.iterdump())
    replace = transaction.os.replace
    failed = False

    def fail_once(src, dest):
        nonlocal failed
        if not failed and Path(src) == path and "archive" in Path(dest).parts:
            failed = True
            raise OSError("simulated disk failure")
        return replace(src, dest)

    monkeypatch.setattr(transaction.os, "replace", fail_once)
    with pytest.raises(OSError, match="simulated"):
        apply_plan(tmp_path, plan_for(tmp_path))
    assert path.exists() and path.with_suffix(".mid").exists()
    with sqlite3.connect(tmp_path / "catalog.db") as conn:
        assert list(conn.iterdump()) == before
    assert not (tmp_path / "listening-admission.json").exists()


def test_duplicate_performance_not_duplicate_title(tmp_path):
    asset(tmp_path, name="title A")
    asset(tmp_path, name="title B")
    plan = make_plan(tmp_path, workers=1)
    assert plan["counts"] == {"inspected": 2, "admitted": 1, "archived": 1}
    assert plan["reason_counts"] == {"duplicate_timed_playback": 1}


def test_noncanonical_encoding_uses_playback_parser(tmp_path, monkeypatch):
    import openorchestrion.library.curation as curation
    path = asset(tmp_path)
    expected = inspect_asset_reference(str(path))

    def unsupported(_raw):
        raise ValueError("noncanonical encoding")

    monkeypatch.setattr(curation, "read_events", unsupported)
    assert inspect_asset(str(path)) == expected
