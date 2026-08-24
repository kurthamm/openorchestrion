from __future__ import annotations

from fastapi.testclient import TestClient

from openorchestrion.app import create_app


def test_setup_assets_and_tab_are_served() -> None:
    with TestClient(create_app()) as client:
        html = client.get("/")
        css = client.get("/setup.css")
        view = client.get("/js/views/setup.js")

    assert html.status_code == 200
    assert 'data-view="setup"' in html.text
    assert 'href="/setup.css"' in html.text
    assert css.status_code == 200
    assert view.status_code == 200


def test_browser_setup_code_has_no_secret_or_system_write_surface() -> None:
    with TestClient(create_app()) as client:
        api_js = client.get("/js/api.js").text
        setup_js = client.get("/js/views/setup.js").text

    assert "OPENAI_API_KEY" not in api_js
    assert "OPENAI_API_KEY" not in setup_js
    assert "/api/setup/complete" in api_js
    assert "/api/setup/reset" in api_js
    assert "openorchestrion-configure" in setup_js
    assert "/etc/openorchestrion" not in setup_js


def test_first_run_auto_route_requires_both_incomplete_and_not_ready() -> None:
    with TestClient(create_app()) as client:
        app_js = client.get("/js/app.js").text

    assert "!data.complete && !data.ready" in app_js
    assert "loadSetup({ autoRoute: true })" in app_js


def test_setup_view_uses_text_only_dom_helper_not_html_injection() -> None:
    with TestClient(create_app()) as client:
        setup_js = client.get("/js/views/setup.js").text

    assert "innerHTML" not in setup_js
    assert "insertAdjacentHTML" not in setup_js
    assert "h(" in setup_js
