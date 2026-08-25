from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from openorchestrion.api.web import WEB_ROOT
from openorchestrion.app import create_app
from openorchestrion.midi import GM_PROGRAM_NAMES


def test_rendering_options_publish_the_backend_gm_vocabulary() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/rendering/options")

    assert response.status_code == 200
    payload = response.json()
    assert payload["modes"] == ["ORIGINAL", "PIANO_ONLY", "OVERRIDE"]
    assert payload["percussion_channel"] == 9
    assert payload["programs"] == [
        {"value": value, "name": name}
        for value, name in enumerate(GM_PROGRAM_NAMES)
    ]
    assert payload["piano_programs"] == payload["programs"][:8]
    assert len(payload["programs"]) == 128


def test_rendering_options_are_published_in_openapi() -> None:
    with TestClient(create_app()) as client:
        schema = client.get("/openapi.json").json()
    assert "/api/rendering/options" in schema["paths"]


def test_rendering_stylesheet_and_panel_ship_with_the_web_app() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/rendering.css").status_code == 200
        shell = client.get("/").text
    assert 'href="/rendering.css"' in shell
    assert 'id="rendering-panel"' in shell


def test_default_original_mode_omits_rendering_from_queue_request() -> None:
    core = (WEB_ROOT / "js" / "rendering.js").read_text(encoding="utf-8")
    api = (WEB_ROOT / "js" / "api.js").read_text(encoding="utf-8")

    assert "if (normalized.mode === 'ORIGINAL') return null" in core
    assert "if (selectedRendering) body.rendering = selectedRendering" in api
    assert "renderingPayload(loadRenderingPreference())" in api


def test_piano_only_and_override_payloads_use_the_public_contract() -> None:
    core = (WEB_ROOT / "js" / "rendering.js").read_text(encoding="utf-8")

    assert "mode: 'PIANO_ONLY'" in core
    assert "piano_program: normalized.pianoProgram" in core
    assert "mode: 'OVERRIDE'" in core
    assert "program_overrides:" in core
    assert "Add at least one channel override" in core


def test_browser_refuses_percussion_and_duplicate_override_channels() -> None:
    core = (WEB_ROOT / "js" / "rendering.js").read_text(encoding="utf-8")
    view = (WEB_ROOT / "js" / "views" / "rendering.js").read_text(encoding="utf-8")

    # MIDI-native channel 9 is human/GM channel 10 percussion.
    assert "channel === 9" in core
    assert "seen.has(channel)" in core
    assert "channel !== percussion" in view
    assert "MIDI channel 10 is percussion" in view


def test_browser_uses_backend_program_names_instead_of_a_second_gm_table() -> None:
    view = (WEB_ROOT / "js" / "views" / "rendering.js").read_text(encoding="utf-8")

    assert "api.renderingOptions()" in view
    assert "options?.programs" in view
    assert "options?.piano_programs" in view
    # A representative canonical GM name must not be hard-coded in browser JS.
    assert "Acoustic Grand Piano" not in view
    assert "GM_PROGRAM_NAMES" not in view


def test_rendering_preference_is_browser_local_not_server_state() -> None:
    store = (WEB_ROOT / "js" / "store.js").read_text(encoding="utf-8")
    core = (WEB_ROOT / "js" / "rendering.js").read_text(encoding="utf-8")
    view = (WEB_ROOT / "js" / "views" / "rendering.js").read_text(encoding="utf-8")

    assert "oo.rendering" in core
    assert "renderingOptions" not in store
    assert "rendering:" not in store
    assert "renderingMounted" in view
    assert "Applies to the next queue" in view


def test_rendering_controls_have_phone_and_kiosk_layout_rules() -> None:
    css = (WEB_ROOT / "rendering.css").read_text(encoding="utf-8")
    assert "@media (max-width: 620px)" in css
    assert "@media (max-height: 520px) and (min-width: 650px)" in css


def test_rendering_css_is_already_covered_by_package_data_glob() -> None:
    # The project deliberately packages all root web CSS rather than naming each
    # stylesheet, so adding rendering.css must not require another packaging seam.
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    source = pyproject.read_text(encoding="utf-8")
    assert '"web/*.css"' in source
