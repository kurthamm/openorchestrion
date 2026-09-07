from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.catalog import rebuild_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.testing.midi_fixtures import generate_suite

COMMAND_ID_1 = "00000000-0000-4000-8000-000000000001"
COMMAND_ID_2 = "00000000-0000-4000-8000-000000000002"
COMMAND_ID_3 = "00000000-0000-4000-8000-000000000003"
COMMAND_ID_4 = "00000000-0000-4000-8000-000000000004"
COMMAND_ID_5 = "00000000-0000-4000-8000-000000000005"


def test_listening_room_api_and_atomic_clear(stocked_client):
    client = stocked_client
    page = client.get('/api/library/browse?limit=2').json()
    assert len(page['items']) == 2 and page['total'] > 2 and page['has_more']
    asset_id = page['items'][0]['asset_id']
    assert client.get(f'/api/library/assets/{asset_id}/performance').status_code == 200
    assert client.get('/api/library/assets/missing/performance').status_code == 404
    assert client.get('/api/library/browse?sort=bad').status_code == 422
    assert client.get('/api/library/browse?offset=-1').status_code == 422
    assert client.get('/api/library/browse/facets').json()['total'] == page['total']
    assert client.post('/api/queue', json={'asset_ids': [asset_id]}).status_code == 200
    assert client.post('/api/transport/play', json={}).status_code == 200
    cleared = client.post('/api/queue/clear', json={'command_id': COMMAND_ID_5})
    assert cleared.status_code == 200
    assert cleared.json()['items'] == [] and cleared.json()['current_index'] is None
    assert not client.get('/api/status').json()['playing']
    # A retry after a lost response cannot erase a newer session.
    client.post('/api/queue', json={'asset_ids': [asset_id]})
    assert len(client.post('/api/queue/clear', json={'command_id': COMMAND_ID_5}).json()['items']) == 1


@pytest.mark.parametrize("endpoint,payload", [
    ("/api/stations/preview", {"intent": {"genres": ["classical"]}}),
    ("/api/concierge/ask", {"prompt": "classical music"}),
    ("/api/queue", {"intent": {"genres": ["classical"]}}),
])
def test_slow_selection_does_not_block_the_event_loop(stocked_client, monkeypatch, endpoint, payload):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from openorchestrion.api import routes

    entered, release = Event(), Event()
    original = routes.build_station
    # A thread executor allows this deliberately blocked fake to share its
    # release event; ordinary endpoint tests use the real spawned process.
    stocked_client.app.state.selection_executor.shutdown()
    stocked_client.app.state.selection_executor = ThreadPoolExecutor(max_workers=1)

    def slow_selection(*args, **kwargs):
        entered.set()
        assert release.wait(5), "selection was never released"
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "build_station", slow_selection)
    with ThreadPoolExecutor(max_workers=2) as callers:
        request = callers.submit(stocked_client.post, endpoint, json=payload)
        try:
            assert entered.wait(3)
            # Health runs on the same event loop as MIDI. It must run before
            # the selector finishes, not just return after its blocking work.
            health = callers.submit(stocked_client.get, "/api/health")
            assert health.result(timeout=1).status_code == 200
            assert not request.done()
        finally:
            release.set()
        assert request.result(timeout=3).status_code == 200


def test_selection_worker_has_a_separate_process(stocked_client):
    import os
    from types import SimpleNamespace
    from openorchestrion.api.routes import _selection

    connection = SimpleNamespace(app=stocked_client.app)
    worker_pid = stocked_client.portal.call(_selection, connection, os.getpid)
    assert worker_pid != os.getpid()


def test_selection_worker_failure_does_not_require_service_restart(stocked_client):
    import os
    from types import SimpleNamespace
    from openorchestrion.api.errors import ApiError
    from openorchestrion.api.routes import _selection

    connection = SimpleNamespace(app=stocked_client.app)
    with pytest.raises(ApiError, match="Retry") as failure:
        stocked_client.portal.call(_selection, connection, os._exit, 1)
    assert failure.value.status_code == 503
    assert stocked_client.portal.call(_selection, connection, os.getpid) != os.getpid()


def _settings(tmp_path: Path, *, with_library: bool) -> Settings:
    root = tmp_path / "library"
    if with_library:
        fixtures = tmp_path / "fixtures"
        generate_suite(fixtures, long_run_minutes=1)
        assert not import_paths([fixtures], root).failed
        rebuild_catalog(root)
    return Settings(
        library_root=root,
        catalog_db=root / "catalog.db",
        history_db=root / "history.db",
        player_state_db=root / "player-state.db",
        virtual_midi=True,
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
    ai = empty_client.get("/api/status").json()["ai"]
    assert ai["enabled"] is True
    assert ai["reason"] == "no_provider_configured_using_offline_interpreter"


def test_status_counts_a_real_library(stocked_client: TestClient) -> None:
    status = stocked_client.get("/api/status").json()
    assert status["library"]["indexed"] is True
    assert status["library"]["assets"] > 0
    assert status["outputs"]["ready"] is True


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
        json={"prompt": "play dinner music for two hours", "command_id": COMMAND_ID_1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["command_id"] == COMMAND_ID_1
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
    assert "relaxations" in body


def test_station_preview_without_catalog_uses_error_envelope(empty_client: TestClient) -> None:
    response = empty_client.post("/api/stations/preview", json={"intent": {}})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "library_empty"


def test_unknown_intent_field_is_a_rendered_error_not_a_crash(empty_client: TestClient) -> None:
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


def test_queue_starts_empty_and_requires_a_catalog_for_population(empty_client: TestClient) -> None:
    response = empty_client.get("/api/queue")
    assert response.status_code == 200
    assert response.json()["items"] == []

    response = empty_client.post(
        "/api/queue",
        json={"intent": {"themes": ["dinner"]}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "library_empty"


def test_queue_and_transport_run_against_virtual_midi(stocked_client: TestClient) -> None:
    asset = stocked_client.get("/api/library/search", params={"limit": 1}).json()["items"][0]
    queued = stocked_client.post(
        "/api/queue",
        json={"asset_ids": [asset["asset_id"]], "command_id": COMMAND_ID_2},
    )
    assert queued.status_code == 200
    assert queued.json()["items"][0]["asset_id"] == asset["asset_id"]
    assert queued.json()["current_index"] == 0

    started = stocked_client.post(
        "/api/transport/play",
        json={"command_id": COMMAND_ID_3},
    )
    assert started.status_code == 200
    assert started.json()["state"] == "playing"
    assert started.json()["now_playing"]["asset_id"] == asset["asset_id"]

    stopped = stocked_client.post(
        "/api/transport/stop",
        json={"command_id": COMMAND_ID_4},
    )
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"


def test_saved_collections_queue_editing_modes_seek_and_timer(stocked_client: TestClient) -> None:
    assets = stocked_client.get("/api/library/search", params={"limit": 2}).json()["items"]
    ids = [item["asset_id"] for item in assets]
    assert stocked_client.post("/api/queue", json={"asset_ids": ids}).status_code == 200

    saved = stocked_client.post("/api/collections", json={"name": "Test set", "kind": "playlist"})
    assert saved.status_code == 200
    collection_id = saved.json()["id"]
    assert stocked_client.get("/api/collections").json()["items"][0]["asset_ids"] == ids

    modes = stocked_client.post(
        "/api/playback/modes",
        json={"repeat_mode": "queue", "shuffle": True, "continuous": True},
    )
    assert modes.json()["repeat_mode"] == "queue"
    assert stocked_client.post("/api/queue/play-next", json={"asset_id": ids[1]}).status_code == 200
    assert stocked_client.post("/api/queue/remove-many", json={"asset_ids": [ids[1]]}).status_code == 200
    assert stocked_client.post(f"/api/collections/{collection_id}/load").status_code == 200

    assert stocked_client.post("/api/transport/play", json={}).status_code == 200
    sought = stocked_client.post("/api/playback/seek", json={"position_seconds": 0.01})
    assert sought.status_code == 200
    timer = stocked_client.post(
        "/api/playback/sleep-timer", json={"seconds": 60, "after_current": False}
    )
    assert timer.json()["sleep_timer_remaining_seconds"] in {59, 60}
    assert stocked_client.delete(f"/api/collections/{collection_id}").status_code == 204


def test_song_preferences_diagnostics_schedule_undo_and_operations(stocked_client: TestClient) -> None:
    asset = stocked_client.get("/api/library/search", params={"limit": 1}).json()["items"][0]
    asset_id = asset["asset_id"]
    saved = stocked_client.put(
        f"/api/library/assets/{asset_id}/preference",
        json={"tempo_percent": 90, "volume_percent": 115},
    )
    assert saved.status_code == 200
    assert stocked_client.get(f"/api/library/assets/{asset_id}/preference").json()["tempo_percent"] == 90
    queued = stocked_client.post("/api/queue", json={"asset_ids": [asset_id]}).json()
    assert queued["items"][0]["tempo_percent"] == 90
    assert stocked_client.post("/api/queue/clear", json={}).json()["can_undo"] is True
    assert stocked_client.post("/api/queue/undo").status_code == 200
    assert stocked_client.post("/api/playback/schedule-start", json={"seconds": 60}).status_code == 200
    assert stocked_client.post("/api/playback/schedule-start", json={"seconds": None}).status_code == 200
    assert stocked_client.post("/api/devices/test-note", json={"duration_seconds": 0.05}).status_code == 204
    operations = stocked_client.get("/api/operations")
    assert operations.status_code == 200
    assert operations.json()["disk_free_bytes"] > 0


def test_playback_routes_publish_real_success_models() -> None:
    with TestClient(create_app()) as client:
        paths = client.get("/openapi.json").json()["paths"]

    def schema_ref(path: str, method: str, status: str) -> str:
        content = paths[path][method]["responses"][status]["content"]
        return content["application/json"]["schema"]["$ref"]

    assert schema_ref("/api/queue", "get", "200").endswith("/QueueState")
    assert schema_ref("/api/queue", "post", "200").endswith("/QueueState")
    assert schema_ref("/api/queue/reorder", "post", "200").endswith("/QueueState")
    assert schema_ref("/api/transport/{action}", "post", "200").endswith("/PlaybackState")
    assert "501" not in paths["/api/queue"]["get"]["responses"]


def test_favorite_persists_and_is_visible_to_search(stocked_client: TestClient) -> None:
    """Favorites are durable now; the endpoint no longer answers 501."""
    asset = stocked_client.get("/api/library/search", params={"limit": 1}).json()["items"][0]
    assert asset["favorite"] is False

    response = stocked_client.post(
        f"/api/library/assets/{asset['asset_id']}/favorite",
        json={"favorite": True},
    )
    assert response.status_code == 200
    assert response.json()["favorite"] is True

    # The rebuildable index was reconciled, so browse reflects it immediately.
    listed = stocked_client.get("/api/library/search", params={"limit": 100}).json()["items"]
    assert next(row for row in listed if row["asset_id"] == asset["asset_id"])["favorite"] is True

    cleared = stocked_client.post(
        f"/api/library/assets/{asset['asset_id']}/favorite",
        json={"favorite": False},
    )
    assert cleared.json()["favorite"] is False


def test_favorite_on_unknown_asset_is_not_found(stocked_client: TestClient) -> None:
    response = stocked_client.post(
        "/api/library/assets/sha256:" + "0" * 64 + "/favorite",
        json={"favorite": True},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "asset_not_found"


def test_favorite_route_no_longer_advertises_501() -> None:
    with TestClient(create_app()) as client:
        paths = client.get("/openapi.json").json()["paths"]
    responses = paths["/api/library/assets/{asset_id}/favorite"]["post"]["responses"]
    assert "501" not in responses
    assert responses["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/LibraryAssetDetail"
    )


def test_unknown_transport_action_is_rejected(empty_client: TestClient) -> None:
    response = empty_client.post("/api/transport/rewind")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "transport_conflict"


def test_devices_reports_virtual_output(stocked_client: TestClient) -> None:
    outputs = stocked_client.get("/api/devices").json()["outputs"]
    assert outputs["ready"] is True
    assert "OpenOrchestrion Virtual" in outputs["devices"]


def test_websocket_starts_with_full_snapshot_and_resyncs(empty_client: TestClient) -> None:
    with empty_client.websocket_connect("/api/ws") as socket:
        first = socket.receive_json()
        assert first["type"] == "state.snapshot"
        assert first["payload"]["playback"]["state"] == "idle"
        assert first["payload"]["queue"]["items"] == []

        socket.send_json({"type": "state.request_snapshot"})
        second = socket.receive_json()
        assert second["type"] == "state.snapshot"
        assert second["seq"] >= first["seq"]


def test_session_id_carries_the_conversation_forward(stocked_client: TestClient) -> None:
    first = stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "play christmas music", "session_id": "kitchen"},
    ).json()
    assert "christmas" in [theme.lower() for theme in first["intent"]["themes"]]

    second = stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "a little more upbeat", "session_id": "kitchen"},
    ).json()
    assert "christmas" in [theme.lower() for theme in second["intent"]["themes"]]


def test_sessions_are_isolated_from_each_other(stocked_client: TestClient) -> None:
    stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "play christmas music", "session_id": "kitchen"},
    )
    other = stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "a little more upbeat", "session_id": "study"},
    ).json()
    assert other["intent"]["themes"] == []


def test_omitting_session_id_is_stateless(stocked_client: TestClient) -> None:
    stocked_client.post("/api/concierge/ask", json={"prompt": "play christmas music"})
    second = stocked_client.post(
        "/api/concierge/ask", json={"prompt": "a little more upbeat"}
    ).json()
    assert second["intent"]["themes"] == []


def test_explicit_current_intent_overrides_the_remembered_one(
    stocked_client: TestClient,
) -> None:
    stocked_client.post(
        "/api/concierge/ask",
        json={"prompt": "play christmas music", "session_id": "kitchen"},
    )
    resynced = stocked_client.post(
        "/api/concierge/ask",
        json={
            "prompt": "a little more upbeat",
            "session_id": "kitchen",
            "current_intent": {"themes": ["ragtime"]},
        },
    ).json()
    assert [theme.lower() for theme in resynced["intent"]["themes"]] == ["ragtime"]


def test_session_store_is_bounded() -> None:
    from openorchestrion.api.sessions import ConciergeSessions

    sessions = ConciergeSessions(max_sessions=2)
    sessions.get("a")
    sessions.get("b")
    sessions.get("c")
    assert len(sessions) == 2
    assert "a" not in sessions


def test_asset_detail_returns_descriptive_tags(stocked_client: TestClient) -> None:
    listed = stocked_client.get("/api/library/search", params={"limit": 1}).json()["items"][0]
    body = stocked_client.get(f"/api/library/assets/{listed['asset_id']}").json()
    assert body["asset_id"] == listed["asset_id"]
    for field in ("genres", "moods", "themes", "instrumentation"):
        assert isinstance(body[field], list)
    assert "midi_path" not in body


def test_asset_detail_missing_asset_is_not_found(stocked_client: TestClient) -> None:
    response = stocked_client.get("/api/library/assets/sha256:nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "asset_not_found"


def test_bad_query_parameter_is_request_invalid_not_intent_invalid(
    empty_client: TestClient,
) -> None:
    response = empty_client.get("/api/library/search", params={"limit": 0})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_invalid"


def test_malformed_queue_command_is_request_invalid(empty_client: TestClient) -> None:
    response = empty_client.post("/api/queue/reorder", json={"to_index": -1})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_invalid"


def test_command_id_must_be_a_uuid(empty_client: TestClient) -> None:
    response = empty_client.post("/api/transport/skip", json={"command_id": "not-a-uuid"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_invalid"


def test_queue_replace_requires_exactly_one_source(empty_client: TestClient) -> None:
    empty = empty_client.post("/api/queue", json={})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "request_invalid"

    ambiguous = empty_client.post(
        "/api/queue",
        json={"intent": {}, "asset_ids": ["sha256:abc"]},
    )
    assert ambiguous.status_code == 422
    assert ambiguous.json()["error"]["code"] == "request_invalid"


def test_intent_body_failure_is_still_intent_invalid(empty_client: TestClient) -> None:
    response = empty_client.post("/api/intent/validate", json={"duration_minutes": 99999})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "intent_invalid"


def test_unexpected_exception_uses_the_error_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    from openorchestrion.api import routes

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("catalog exploded")

    monkeypatch.setattr(routes, "_outputs_state", boom)
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get("/api/devices")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "catalog exploded" not in response.text


def test_position_anchor_documents_the_clock_rule() -> None:
    from openorchestrion.api.models import PositionAnchor

    description = PositionAnchor.model_fields["server_time"].description or ""
    assert "diagnostic" in description.lower()
    assert "anchor" in (PositionAnchor.__doc__ or "").lower()


def test_openapi_schema_publishes_the_contract(empty_client: TestClient) -> None:
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


def test_facets_reflect_the_catalog(stocked_client: TestClient, empty_client: TestClient) -> None:
    empty = empty_client.get("/api/library/facets").json()
    assert all(empty[key] == [] for key in ("genres", "moods", "themes", "eras", "composers"))
    body = stocked_client.get("/api/library/facets", params={"limit": 5}).json()
    assert body["indexed"] is True
    for key in ("genres", "moods", "themes", "eras", "composers"):
        assert isinstance(body[key], list) and len(body[key]) <= 5
        for entry in body[key]:
            assert entry["count"] >= 1 and entry["value"]
    assert stocked_client.get("/api/library/facets", params={"limit": 0}).status_code == 422
