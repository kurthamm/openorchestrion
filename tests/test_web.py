from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openorchestrion.api.web import WEB_ROOT
from openorchestrion.app import create_app

JS_FILES = sorted(WEB_ROOT.glob("js/**/*.js"))
REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_app_shell_is_served(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "OpenOrchestrion" in response.text
    assert response.headers["cache-control"] == "no-store"


def test_static_assets_are_served(client: TestClient) -> None:
    for path in ("/app.css", "/js/app.js", "/icon.svg", "/manifest.webmanifest"):
        assert client.get(path).status_code == 200, path


def test_web_mount_does_not_shadow_the_api(client: TestClient) -> None:
    """The catch-all mount at / is registered last for exactly this reason."""
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/openapi.json").status_code == 200


def test_unknown_path_is_not_html(client: TestClient) -> None:
    assert client.get("/api/definitely-not-a-route").status_code == 404


def test_security_headers_forbid_external_origins(client: TestClient) -> None:
    """The appliance must work offline, so no third-party origin is loadable."""
    csp = client.get("/").headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "connect-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp


def test_api_responses_are_not_given_the_web_csp(client: TestClient) -> None:
    assert "content-security-policy" not in client.get("/api/health").headers


@pytest.mark.parametrize("path", [p for p in JS_FILES], ids=lambda p: p.name)
def test_no_external_resources_referenced(path: Path) -> None:
    """Nothing may be fetched from another origin; the Pi may have no Internet."""
    source = path.read_text(encoding="utf-8")
    assert "http://" not in source
    assert not re.search(r"https://(?!json-schema|openorchestrion)", source)


def test_markup_references_no_external_origins() -> None:
    markup = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert "//fonts." not in markup
    assert "cdn" not in markup.lower()
    assert "http://" not in markup


def test_stylesheet_uses_system_fonts_only() -> None:
    css = (WEB_ROOT / "app.css").read_text(encoding="utf-8")
    assert "@import" not in css
    assert "system-ui" in css


def test_package_data_includes_shell_and_nested_modules() -> None:
    """Editable installs can hide bad package-data globs; wheels cannot."""
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = set(config["tool"]["setuptools"]["package-data"]["openorchestrion"])
    required = {
        "web/*.html",
        "web/*.css",
        "web/*.svg",
        "web/*.webmanifest",
        "web/js/*.js",
        "web/js/views/*.js",
    }
    assert required.issubset(patterns)


def test_no_innerhtml_assignment_anywhere() -> None:
    """Library metadata is user-supplied; it is rendered as text, never markup."""
    unsafe = re.compile(r"(innerHTML|outerHTML|insertAdjacentHTML)\s*(=[^=]|\()")
    for path in JS_FILES:
        found = unsafe.search(path.read_text(encoding="utf-8"))
        assert found is None, f"{path.name}: {found.group(0) if found else ''}"


def test_every_module_is_reachable_from_the_entry_point() -> None:
    """Guards against a view file that was written but never wired up."""
    seen: set[Path] = set()
    pending = [WEB_ROOT / "js" / "app.js"]
    while pending:
        current = pending.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        for match in re.findall(r"from\s+'([^']+)'", current.read_text(encoding="utf-8")):
            if match.startswith("."):
                pending.append((current.parent / match).resolve())
    assert seen == set(JS_FILES)


def test_hidden_views_are_actually_hidden() -> None:
    """`.view {display:flex}` outranks the UA `[hidden]` rule."""
    css = (WEB_ROOT / "app.css").read_text(encoding="utf-8")
    assert re.search(r"\.view\[hidden\]\s*\{[^}]*display:\s*none", css)


def test_position_module_does_not_trust_the_server_clock() -> None:
    """Contract D1: anchoring on server_time would break on clock skew."""
    source = (WEB_ROOT / "js" / "position.js").read_text(encoding="utf-8")
    assert "performance.now()" in source
    assert "position.server_time" not in source
    assert "Date.parse(position" not in source


def test_socket_resyncs_on_a_sequence_gap() -> None:
    """Contract D2: a gap means snapshot, not patch."""
    source = (WEB_ROOT / "js" / "socket.js").read_text(encoding="utf-8")
    assert "requestSnapshot" in source
    assert "state.request_snapshot" in source


def test_socket_counts_error_envelopes_in_sequence() -> None:
    """An error at seq N must not make the next state at N+1 look like a gap."""
    source = (WEB_ROOT / "js" / "socket.js").read_text(encoding="utf-8")
    assert source.index("typeof envelope.seq") < source.index("envelope.type === 'error'")


def test_transport_commands_carry_an_idempotency_id() -> None:
    """Contract D4: a retry after a dropped connection must not double-skip."""
    source = (WEB_ROOT / "js" / "api.js").read_text(encoding="utf-8")
    assert "commandId()" in source
    assert "randomUUID" in source
    assert "transport: (action, id = commandId())" in source


def test_transport_can_reconcile_from_websocket_confirmation() -> None:
    """The same command id must be visible to REST and WebSocket state."""
    source = (WEB_ROOT / "js" / "app.js").read_text(encoding="utf-8")
    assert "pendingCommandId" in source
    assert "api.transport(action, id)" in source
    assert "playback?.command_id === pendingId" in source


def test_correlation_ids_stay_out_of_the_intent() -> None:
    """Contract D5: PlaybackIntent forbids extra fields."""
    source = (WEB_ROOT / "js" / "api.js").read_text(encoding="utf-8")
    intent_call = source[source.index("stationPreview:") : source.index("search:")]
    assert "command_id" not in intent_call
