from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.setup_state import SETUP_VERSION, setup_path
from openorchestrion.testing.midi_fixtures import generate_suite


def _settings(tmp_path: Path, *, with_library: bool) -> Settings:
    library = tmp_path / "library"
    state = tmp_path / "state"
    state.mkdir(parents=True, exist_ok=True)
    if with_library:
        fixtures = tmp_path / "fixtures"
        generate_suite(fixtures, long_run_minutes=1)
        assert not import_paths([fixtures], library).failed
        rebuild_catalog(library)
    return Settings(
        library_root=library,
        catalog_db=library / "catalog.db",
        history_db=state / "history.db",
        virtual_midi=True,
    )


def test_first_run_reports_incomplete_and_missing_library(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=False)
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/api/setup")

    assert response.status_code == 200
    body = response.json()
    assert body["wizard_version"] == SETUP_VERSION
    assert body["complete"] is False
    assert body["ready"] is False
    assert body["outputs"]["ready"] is True
    assert body["library"]["indexed"] is False
    assert any("Import MIDI" in step for step in body["next_steps"])


def test_stocked_virtual_appliance_is_ready_even_with_offline_concierge(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    with TestClient(create_app(settings=settings)) as client:
        body = client.get("/api/setup").json()

    assert body["ready"] is True
    assert body["ai"]["enabled"] is True
    assert body["ai"]["provider"] == "deterministic-fallback"
    assert body["complete"] is False
    assert any("core appliance is ready" in step for step in body["next_steps"])


def test_complete_marker_survives_application_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    marker = setup_path(settings.history_db.parent)

    with TestClient(create_app(settings=settings)) as client:
        body = client.post("/api/setup/complete").json()
        assert body["complete"] is True
        assert body["completed_at"]

    assert marker.is_file()
    stored = json.loads(marker.read_text(encoding="utf-8"))
    assert stored["version"] == SETUP_VERSION

    with TestClient(create_app(settings=settings)) as client:
        again = client.get("/api/setup").json()
    assert again["complete"] is True
    assert again["completed_at"] == body["completed_at"]


def test_reset_is_harmless_and_does_not_change_readiness(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    with TestClient(create_app(settings=settings)) as client:
        client.post("/api/setup/complete")
        body = client.post("/api/setup/reset").json()

    assert body["complete"] is False
    assert body["ready"] is True
    assert body["marker_reason"] == "not_completed"


def test_malformed_marker_is_incomplete_not_a_boot_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    marker = setup_path(settings.history_db.parent)
    marker.write_text("{not-json", encoding="utf-8")

    with TestClient(create_app(settings=settings)) as client:
        body = client.get("/api/setup").json()

    assert body["complete"] is False
    assert body["marker_reason"] == "marker_unreadable"
    assert body["ready"] is True


def test_setup_marker_never_gates_normal_application_api(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    with TestClient(create_app(settings=settings)) as client:
        assert client.get("/api/setup").json()["complete"] is False
        search = client.get("/api/library/search", params={"limit": 1})
        status = client.get("/api/status")

    assert search.status_code == 200
    assert search.json()["count"] == 1
    assert status.status_code == 200


def test_browser_setup_write_endpoints_accept_no_configuration_body(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=False)
    with TestClient(create_app(settings=settings)) as client:
        schema = client.get("/openapi.json").json()

    complete = schema["paths"]["/api/setup/complete"]["post"]
    reset = schema["paths"]["/api/setup/reset"]["post"]
    assert "requestBody" not in complete
    assert "requestBody" not in reset

    serialized = json.dumps(schema)
    # Provider keys are local-admin configuration and must never become a web API field.
    assert "OPENAI_API_KEY" not in serialized


def test_first_run_auto_route_retries_after_initial_setup_fetch_failure() -> None:
    """A startup race must not permanently consume the one-shot setup redirect."""
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "openorchestrion"
        / "web"
        / "js"
        / "app.js"
    ).read_text(encoding="utf-8")

    # The failure path must preserve setup.autoRouted instead of marking a
    # decision that never happened.
    assert "loading: false, error, autoRouted: true" not in source
    # One call happens at startup; the second is the retry after WebSocket live.
    assert source.count("loadSetup({ autoRoute: true })") >= 2
