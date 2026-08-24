from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import openorchestrion.backup_operator as operator
from openorchestrion.backup import create_backup, restore_backup
from openorchestrion.backup_operator import OperatorError, inspect_backup, replace_from_backup
from openorchestrion.history import mark_completed, mark_started, queue_play
from openorchestrion.library.catalog import get_asset, rebuild_catalog, search_catalog
from openorchestrion.library.importer import import_midi
from openorchestrion.library.metadata import update_metadata
from openorchestrion.testing.midi_fixtures import generate_suite


def _state(base: Path, name: str, *, fixture: str, title: str) -> tuple[Path, str]:
    fixtures = base / f"fixtures-{name}"
    generate_suite(fixtures, long_run_minutes=1)
    root = base / name
    result = import_midi(fixtures / fixture, root / "library")
    asset_id = f"sha256:{result.asset_id}"
    update_metadata(root / "library", asset_id, {"title": title, "favorite": True})
    rebuild_catalog(root / "library")
    play_id = queue_play(
        root / "history.db",
        asset_id=asset_id,
        track_duration_seconds=30,
        occurred_at="2026-08-24T01:00:00+00:00",
    )
    mark_started(root / "history.db", play_id, occurred_at="2026-08-24T01:00:01+00:00")
    mark_completed(
        root / "history.db",
        play_id,
        occurred_at="2026-08-24T01:00:31+00:00",
        played_seconds=30,
    )
    return root, asset_id


def _title(root: Path) -> str:
    row = search_catalog(root / "library" / "catalog.db", limit=1)[0]
    return str(row["title"])


def _mock_root_service(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
    monkeypatch.setattr(operator.os, "geteuid", lambda: 0)
    monkeypatch.setattr(operator, "_stop_service", lambda service: calls.append(f"stop:{service}"))
    monkeypatch.setattr(operator, "_start_service", lambda service: calls.append(f"start:{service}"))


def test_inspect_fully_verifies_without_publishing_state(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, "source", fixture="single-note.mid", title="Source")
    archive = tmp_path / "backup.zip"
    create_backup(root, archive)

    report = inspect_backup(archive)

    assert report.asset_count == 1
    assert report.file_count == 3
    assert report.history_included is True
    assert report.archive == str(archive.absolute())
    assert not any(path.name == "state" for path in tmp_path.iterdir() if path.is_dir() and path != root)


def test_fresh_installer_skeleton_can_be_replaced_without_replace_flag(tmp_path: Path) -> None:
    source, _ = _state(tmp_path, "source", fixture="single-note.mid", title="Restored")
    archive = tmp_path / "backup.zip"
    create_backup(source, archive)

    target = tmp_path / "target"
    (target / "library" / "assets").mkdir(parents=True)
    (target / "setup.json").write_text('{"version": 1}\n')

    report = replace_from_backup(archive, target, manage_service=False)

    assert report.rollback_archive is None
    assert report.service_managed is False
    assert _title(target) == "Restored"
    assert not (target / "setup.json").exists()


def test_existing_durable_state_is_refused_without_explicit_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    archive = tmp_path / "new.zip"
    create_backup(new, archive)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)

    with pytest.raises(OperatorError, match="--replace-existing"):
        replace_from_backup(archive, old, health_url="http://example.invalid")

    assert calls == []
    assert _title(old) == "Old"


def test_symlinked_catalog_is_not_mistaken_for_disposable_skeleton_state(tmp_path: Path) -> None:
    root = tmp_path / "state"
    (root / "library" / "assets").mkdir(parents=True)
    external = tmp_path / "external.db"
    external.write_bytes(b"not-the-real-catalog")
    (root / "library" / "catalog.db").symlink_to(external)

    assert operator._state_has_durable_payload(root) is True


def test_invalid_archive_never_stops_service_or_changes_live_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)

    with pytest.raises(Exception):
        replace_from_backup(
            bad,
            live,
            replace_existing=True,
            health_url="http://example.invalid",
        )

    assert calls == []
    assert _title(live) == "Old"


def test_prepare_failure_never_stops_healthy_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    create_backup(new, incoming)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)
    monkeypatch.setattr(operator, "REFERENCE_STATE_ROOT", live.absolute())
    monkeypatch.setattr(
        operator,
        "_apply_reference_state_permissions",
        lambda root: (_ for _ in ()).throw(OperatorError("permission prep failed")),
    )

    with pytest.raises(OperatorError, match="permission prep failed"):
        replace_from_backup(
            incoming,
            live,
            replace_existing=True,
            rollback_archive=tmp_path / "rollback.zip",
            health_url="http://example.invalid",
        )

    assert calls == []
    assert _title(live) == "Old"


def test_restore_source_must_live_outside_state_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = live / "incoming.zip"
    create_backup(new, incoming)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)

    with pytest.raises(OperatorError, match="outside the state root"):
        replace_from_backup(incoming, live, replace_existing=True)

    assert calls == []
    assert _title(live) == "Old"


def test_rollback_archive_must_live_outside_state_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    create_backup(new, incoming)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)

    with pytest.raises(OperatorError, match="rollback archive must live outside"):
        replace_from_backup(
            incoming,
            live,
            replace_existing=True,
            rollback_archive=live / "rollback.zip",
        )

    assert calls == []
    assert _title(live) == "Old"


def test_successful_replacement_keeps_verified_rollback_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    rollback = tmp_path / "rollback.zip"
    create_backup(new, incoming)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)
    monkeypatch.setattr(operator, "_wait_service_health", lambda url, timeout_seconds: calls.append("health"))

    report = replace_from_backup(
        incoming,
        live,
        replace_existing=True,
        rollback_archive=rollback,
        health_url="http://127.0.0.1:9999",
    )

    assert _title(live) == "New"
    assert report.rollback_archive == str(rollback.absolute())
    assert rollback.is_file()
    assert calls == ["stop:openorchestrion.service", "start:openorchestrion.service", "health"]
    assert not list(tmp_path.glob(".live.previous.*"))

    restored_old = tmp_path / "restored-old"
    restore_backup(rollback, restored_old)
    assert _title(restored_old) == "Old"


def test_failed_new_service_health_restores_exact_original_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, old_asset = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    rollback = tmp_path / "rollback.zip"
    create_backup(new, incoming)
    before_sidecar = next((live / "library" / "assets").glob("*.json")).read_bytes()
    before_history = (live / "history.db").read_bytes()
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)
    health_calls = 0

    def health(url: str, *, timeout_seconds: float) -> None:
        nonlocal health_calls
        health_calls += 1
        calls.append(f"health:{health_calls}")
        if health_calls == 1:
            raise OperatorError("new tree failed health")

    monkeypatch.setattr(operator, "_wait_service_health", health)

    with pytest.raises(OperatorError, match="original state was restored"):
        replace_from_backup(
            incoming,
            live,
            replace_existing=True,
            rollback_archive=rollback,
            health_url="http://127.0.0.1:9999",
        )

    assert _title(live) == "Old"
    assert get_asset(live / "library" / "catalog.db", old_asset) is not None
    assert next((live / "library" / "assets").glob("*.json")).read_bytes() == before_sidecar
    assert (live / "history.db").read_bytes() == before_history
    assert rollback.is_file()
    assert calls == [
        "stop:openorchestrion.service",
        "start:openorchestrion.service",
        "health:1",
        "stop:openorchestrion.service",
        "start:openorchestrion.service",
        "health:2",
    ]
    assert not list(tmp_path.glob(".live.failed.*"))


def test_double_health_failure_preserves_failed_tree_and_rollback_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live, _ = _state(tmp_path, "live", fixture="single-note.mid", title="Old")
    new, _ = _state(tmp_path, "new", fixture="velocity-ladder.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    rollback = tmp_path / "rollback.zip"
    create_backup(new, incoming)
    calls: list[str] = []
    _mock_root_service(monkeypatch, calls)

    def fail_health(url: str, *, timeout_seconds: float) -> None:
        raise OperatorError("still unhealthy")

    monkeypatch.setattr(operator, "_wait_service_health", fail_health)

    with pytest.raises(OperatorError, match="did not become healthy"):
        replace_from_backup(
            incoming,
            live,
            replace_existing=True,
            rollback_archive=rollback,
            health_url="http://127.0.0.1:9999",
        )

    assert _title(live) == "Old"
    assert rollback.is_file()
    failed = list(tmp_path.glob(".live.failed.*"))
    assert len(failed) == 1
    assert _title(failed[0]) == "New"


def test_reference_restore_requires_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, _ = _state(tmp_path, "source", fixture="single-note.mid", title="New")
    archive = tmp_path / "incoming.zip"
    create_backup(source, archive)
    reference = tmp_path / "reference"
    monkeypatch.setattr(operator, "REFERENCE_STATE_ROOT", reference.absolute())
    monkeypatch.setattr(operator.os, "geteuid", lambda: 1000)

    with pytest.raises(OperatorError, match="requires root"):
        replace_from_backup(archive, reference)

    assert not reference.exists()


def test_reference_permission_application_is_bounded_to_state_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reference"
    (root / "library" / "assets").mkdir(parents=True)
    asset = root / "library" / "assets" / "piece.mid"
    asset.write_bytes(b"midi")
    sibling = tmp_path / "do-not-touch"
    sibling.write_text("sentinel")
    monkeypatch.setattr(operator.pwd, "getpwnam", lambda name: type("P", (), {"pw_uid": 123})())
    monkeypatch.setattr(operator.grp, "getgrnam", lambda name: type("G", (), {"gr_gid": 456})())
    touched: list[Path] = []
    monkeypatch.setattr(operator.os, "chown", lambda path, uid, gid: touched.append(Path(path)))

    operator._apply_reference_state_permissions(root.absolute())

    assert root in touched
    assert asset in touched
    assert sibling not in touched
    assert sibling.read_text() == "sentinel"
    assert root.stat().st_mode & 0o777 == 0o750
    assert asset.stat().st_mode & 0o777 == 0o640


def test_reference_restore_prepares_candidate_permissions_before_service_stop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _ = _state(tmp_path, "source", fixture="single-note.mid", title="New")
    incoming = tmp_path / "incoming.zip"
    create_backup(source, incoming)
    reference = tmp_path / "reference"
    (reference / "library" / "assets").mkdir(parents=True)
    calls: list[str] = []
    monkeypatch.setattr(operator, "REFERENCE_STATE_ROOT", reference.absolute())
    _mock_root_service(monkeypatch, calls)
    prepared: list[Path] = []

    def prepare(root: Path) -> None:
        prepared.append(root)

    monkeypatch.setattr(operator, "_apply_reference_state_permissions", prepare)
    monkeypatch.setattr(operator, "_wait_service_health", lambda url, timeout_seconds: calls.append("health"))

    replace_from_backup(
        incoming,
        reference,
        health_url="http://127.0.0.1:9999",
    )

    assert len(prepared) == 1
    assert prepared[0] != reference
    assert prepared[0].name.startswith(".reference.candidate.")
    assert calls == ["stop:openorchestrion.service", "start:openorchestrion.service", "health"]


def test_no_service_control_is_forbidden_for_reference_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, _ = _state(tmp_path, "source", fixture="single-note.mid", title="New")
    archive = tmp_path / "incoming.zip"
    create_backup(source, archive)
    reference = tmp_path / "reference"
    monkeypatch.setattr(operator, "REFERENCE_STATE_ROOT", reference.absolute())
    monkeypatch.setattr(operator.os, "geteuid", lambda: 0)

    with pytest.raises(OperatorError, match="may not disable service control"):
        replace_from_backup(archive, reference, manage_service=False)


def test_cli_create_refuses_destination_inside_state_root(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, "source", fixture="single-note.mid", title="Source")
    destination = root / "backup.zip"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "openorchestrion.backup_operator",
            "create",
            str(destination),
            "--state-root",
            str(root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "outside the state root" in result.stderr
    assert not destination.exists()


def test_cli_create_and_inspect_json_are_secret_free(tmp_path: Path) -> None:
    root, _ = _state(tmp_path, "source", fixture="single-note.mid", title="Source")
    archive = tmp_path / "backup.zip"
    env = dict(os.environ)
    env["OPENAI_API_KEY"] = "sk-secret-that-must-not-appear"

    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "openorchestrion.backup_operator",
            "create",
            str(archive),
            "--state-root",
            str(root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    inspected = subprocess.run(
        [
            sys.executable,
            "-m",
            "openorchestrion.backup_operator",
            "inspect",
            str(archive),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert created.returncode == 0, created.stderr
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(created.stdout)["asset_count"] == 1
    assert json.loads(inspected.stdout)["asset_count"] == 1
    assert "sk-secret" not in created.stdout
    assert "sk-secret" not in inspected.stdout
