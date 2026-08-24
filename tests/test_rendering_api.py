from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from openorchestrion.api.models import QueueReplaceRequest
from openorchestrion.api.routes import _queue_specs
from openorchestrion.api.settings import Settings
from openorchestrion.app import create_app
from openorchestrion.library.catalog import rebuild_catalog, search_catalog
from openorchestrion.library.importer import import_paths
from openorchestrion.models import PlaybackIntent
from openorchestrion.playback import ProgramOverride, RenderingMode, RenderingPolicy
from openorchestrion.testing.midi_fixtures import generate_suite


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
        virtual_midi=True,
    )


def _asset_id(settings: Settings) -> str:
    return search_catalog(settings.catalog_db, limit=1)[0]["asset_id"]


def test_rendering_request_resolves_names_through_the_domain_boundary() -> None:
    payload = QueueReplaceRequest.model_validate(
        {
            "asset_ids": ["sha256:" + "0" * 64],
            "rendering": {
                "mode": "PIANO_ONLY",
                "piano_program": "Honky-tonk Piano",
                "program_overrides": [
                    {"channel": 1, "program": "Violin"},
                    {"channel": 2, "program": 24},
                ],
            },
        }
    )

    assert payload.rendering is not None
    policy = payload.rendering.to_policy()
    assert policy.mode is RenderingMode.PIANO_ONLY
    assert policy.piano_program == 3
    assert policy.program_overrides == (
        ProgramOverride(channel=1, program=40),
        ProgramOverride(channel=2, program=24),
    )


def test_omitted_rendering_preserves_the_existing_queue_semantics(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    payload = QueueReplaceRequest(asset_ids=[_asset_id(settings)])

    specs = _queue_specs(payload, settings)

    assert len(specs) == 1
    assert specs[0].rendering_policy is None


def test_rendering_policy_reaches_the_queue_item_spec(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    payload = QueueReplaceRequest.model_validate(
        {
            "asset_ids": [_asset_id(settings)],
            "rendering": {
                "mode": "PIANO_ONLY",
                "piano_program": "Bright Acoustic Piano",
            },
        }
    )

    specs = _queue_specs(payload, settings)

    assert len(specs) == 1
    assert specs[0].rendering_policy == RenderingPolicy.from_values(
        mode="PIANO_ONLY",
        piano_program="Bright Acoustic Piano",
    )


def test_rendering_policy_reaches_every_smart_station_item(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=True)
    payload = QueueReplaceRequest(
        intent=PlaybackIntent(),
        max_tracks=4,
        rendering={"mode": "PIANO_ONLY"},
    )

    specs = _queue_specs(payload, settings)

    assert specs
    expected = RenderingPolicy.from_values(mode="PIANO_ONLY")
    assert all(spec.rendering_policy == expected for spec in specs)


@pytest.mark.parametrize(
    "rendering",
    [
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": []},
            id="override-needs-target",
        ),
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": [{"channel": 9, "program": "Violin"}]},
            id="percussion-channel",
        ),
        pytest.param(
            {
                "mode": "OVERRIDE",
                "program_overrides": [
                    {"channel": 2, "program": "Violin"},
                    {"channel": 2, "program": "Flute"},
                ],
            },
            id="duplicate-channel",
        ),
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": [{"channel": 1, "program": "strings"}]},
            id="ambiguous-program-name",
        ),
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": [{"channel": 1, "program": "1"}]},
            id="numeric-string",
        ),
        pytest.param(
            {"mode": "PIANO_ONLY", "piano_program": "Violin"},
            id="non-piano-piano-program",
        ),
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": [{"channel": 16, "program": "Violin"}]},
            id="channel-out-of-range",
        ),
        pytest.param(
            {"mode": "OVERRIDE", "program_overrides": [{"channel": 1, "program": True}]},
            id="boolean-program",
        ),
    ],
)
def test_invalid_rendering_fails_during_request_validation(rendering: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        QueueReplaceRequest.model_validate(
            {
                "asset_ids": ["sha256:" + "0" * 64],
                "rendering": rendering,
            }
        )


@pytest.mark.parametrize(
    "rendering",
    [
        {"mode": "OVERRIDE", "program_overrides": []},
        {"mode": "OVERRIDE", "program_overrides": [{"channel": 9, "program": "Violin"}]},
        {"mode": "PIANO_ONLY", "piano_program": "Violin"},
    ],
)
def test_http_reports_bad_rendering_as_request_invalid(
    tmp_path: Path,
    rendering: dict[str, object],
) -> None:
    settings = _settings(tmp_path, with_library=False)
    with TestClient(create_app(settings=settings)) as client:
        response = client.post(
            "/api/queue",
            json={
                "asset_ids": ["sha256:" + "0" * 64],
                "rendering": rendering,
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_invalid"


def test_openapi_publishes_rendering_on_queue_requests(tmp_path: Path) -> None:
    settings = _settings(tmp_path, with_library=False)
    with TestClient(create_app(settings=settings)) as client:
        schema = client.get("/openapi.json").json()["components"]["schemas"]

    queue = schema["QueueReplaceRequest"]
    assert "rendering" in queue["properties"]
    rendering = schema["RenderingRequest"]
    assert set(rendering["properties"]) == {"mode", "piano_program", "program_overrides"}
    assert rendering["additionalProperties"] is False
