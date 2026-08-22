from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.testing.midi_fixtures import generate_suite


def _settings(tmp_path: Path, *, with_library: bool) -> Settings:
    root = tmp_path / "library"
    if with_library:
        fixtures = tmp_path / "fixtures"
        generate_suite(fixtures, long_run_minutes=1)
        import_paths([fixtures], root)
        rebuild_catalog(root)
    return Settings(
        library_root=root,
        catalog_db=root / "catalog.db",
        history_db=root / "history.db",
    )


@pytest.fixture
def empty_client(tmp_path: Path):
    with TestClient(create_app(settings=_settings(tmp_path, with_library=False))) as client:
        yield client


@pytest.fixture
def stocked_client(tmp_path: Path):
    with TestClient(create_app(settings=_settings(tmp_path, with_library=True))) as client:
        yield client


def test_health(empty_client: TestClient) -> None:
    assert empty_client.get("/api/health").json() == {"status": "ok"}


def test_status_reports_missing_library_as_degraded_not_error(empty_client: TestClient) -> None:
    body = empty_client.get("/api/status").json()
    assert body["phase"] == "degraded"
    assert body["library"] == {
        "indexed": False,
        "assets": 0,
        "compositions": 0,
        "genres": 0,
        "moods": 0,
        "themes": 0,
    }


def test_status_reports_offline_interpreter_as_enabled(empty_client: TestClient) -> None:
    """Natural language works with no provider, so the UI must not hide it."""
    ai = empty_client.get("/api/status").json()["ai"]
    assert ai["enabled"] is True
    assert ai["reason"] == "no_provider_configured_using_offline_interpreter"


def test_status_counts_a_real_library(stocked_client: TestClient) -> None:
    library = stocked_client.get("/api/status").json()["library"]
    assert library["indexed"] is True
    assert library["assets"] > 0


def test_search_on_missing_catalog_is_empty_not_an_error(empty_client: TestClient) -> None:
    response = empty_client.get("/api/library/search")
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


def test_search_returns_indexed_assets(stocked_client: TestClient) -> None:
    body = stocked_client.get("/api/library/search", params={"limit": 5}).json()
    assert body["count"] == len(body["items"]) > 0
    assert "asset_id" in body["items"][0]


def test_concierge_answers_offline(stocked_client: TestClient) -> None:
    response = stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "play dinner music for two hours", "command_id": "abc-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["command_id"] == "abc-123"
    assert body["intent"]["duration_minutes"] == 120
    assert body["preview"] is not None


def test_concierge_preview_absent_without_a_catalog(empty_client: TestClient) -> None:
    body = empty_client.post("/api/concierge/ask", json={"prompt": "dinner music"}).json()
    assert body["preview"] is None
    assert body["intent"] is not None


def test_station_preview_returns_explainable_queue(stocked_client: TestClient) -> None:
    response = stocked_client.post(
        "/api/stations/preview",
        json={"intent": {"themes": ["dinner"]}, "seed": 42, "max_tracks": 3},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 3
    assert body["seed"] == 42
    # Relaxations must survive to the client so the appliance can explain itself.
    assert "relaxations" in body


def test_station_preview_without_catalog_uses_error_envelope(empty_client: TestClient) -> None:
    response = empty_client.post("/api/stations/preview", json={"intent": {}})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "library_empty"


def test_unknown_intent_field_is_a_rendered_error_not_a_crash(empty_client: TestClient) -> None:
    """PlaybackIntent forbids extra fields; the UI still needs a usable error."""
    response = empty_client.post(
        "/api/stations/preview",
        json={"intent": {"themes": ["dinner"], "client_hint": "nope"}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "intent_invalid"


def test_history_on_missing_database_is_empty(empty_client: TestClient) -> None:
    assert empty_client.get("/api/history/recent").json() == {"items": [], "count": 0}


def test_history_request_does_not_create_a_database(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=False)
    with TestClient(create_app(settings=settings)) as client:
        client.get("/api/history/recent")
    assert not settings.history_db.exists()


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/queue"),
        ("post", "/api/queue"),
        ("post", "/api/queue/reorder"),
        ("post", "/api/queue/remove"),
        ("post", "/api/transport/play"),
        ("post", "/api/transport/panic"),
        ("post", "/api/library/assets/sha256:abc/favorite"),
    ],
)
def test_playback_endpoints_declare_themselves_pending(
    empty_client: TestClient, method: str, path: str
) -> None:
    response = getattr(empty_client, method)(path)
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_unknown_transport_action_is_rejected(empty_client: TestClient) -> None:
    response = empty_client.post("/api/transport/rewind")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "transport_conflict"


def test_devices_reports_state_without_failing(empty_client: TestClient) -> None:
    outputs = empty_client.get("/api/devices").json()["outputs"]
    assert isinstance(outputs["ready"], bool)
    if not outputs["ready"]:
        assert outputs["reason"]


def test_websocket_accepts_and_reports_pending(empty_client: TestClient) -> None:
    with empty_client.websocket_connect("/api/ws") as socket:
        envelope = socket.receive_json()
    assert envelope["type"] == "error"
    assert envelope["payload"]["code"] == "not_implemented"
    assert envelope["seq"] == 0


def test_openapi_schema_publishes_the_contract(empty_client: TestClient) -> None:
    """The generated schema is what a frontend client is built from."""
    paths = empty_client.get("/openapi.json").json()["paths"]
    for path in (
        "/api/status",
        "/api/concierge/ask",
        "/api/stations/preview",
        "/api/library/search",
        "/api/history/recent",
        "/api/queue",
        "/api/transport/{action}",
    ):
        assert path in paths
