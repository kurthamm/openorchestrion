from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from openorchestrion import appliance
from openorchestrion.api.settings import Settings


def test_server_options_are_environment_driven_and_single_process_safe() -> None:
    options = appliance.server_options(
        {
            "OPENORCHESTRION_HOST": "127.0.0.1",
            "OPENORCHESTRION_PORT": "8123",
            "OPENORCHESTRION_LOG_LEVEL": "warning",
        }
    )
    assert options.host == "127.0.0.1"
    assert options.port == 8123
    assert options.log_level == "warning"


def test_shared_env_file_is_loaded_with_process_overrides(tmp_path: Path) -> None:
    env_file = tmp_path / "openorchestrion.env"
    env_file.write_text(
        "# appliance\n"
        "OPENORCHESTRION_LIBRARY_ROOT=/var/lib/openorchestrion/library\n"
        "OPENORCHESTRION_PORT=8000\n"
        "OPENORCHESTRION_LOG_LEVEL='info'\n",
        encoding="utf-8",
    )
    env = appliance.load_appliance_environment(
        {"OPENORCHESTRION_PORT": "8123"},
        config_path=env_file,
    )
    assert env["OPENORCHESTRION_LIBRARY_ROOT"] == "/var/lib/openorchestrion/library"
    assert env["OPENORCHESTRION_PORT"] == "8123"
    assert env["OPENORCHESTRION_LOG_LEVEL"] == "info"
    assert appliance.server_options(env).port == 8123
    assert appliance._kiosk_url(env) == "http://127.0.0.1:8123"


@pytest.mark.parametrize("value", ["zero", "0", "65536"])
def test_server_port_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        appliance.server_options({"OPENORCHESTRION_PORT": value})


def test_serve_entrypoint_always_uses_one_uvicorn_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    captured: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setenv("OPENORCHESTRION_HOST", "127.0.0.1")
    monkeypatch.setenv("OPENORCHESTRION_PORT", "8765")
    monkeypatch.setattr(uvicorn, "run", fake_run)
    appliance.serve_main()

    assert captured["app"] == "openorchestrion.app:app"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 8765
    assert captured["workers"] == 1
    assert captured["reload"] is False


def test_deployment_files_are_exportable_from_package(tmp_path: Path) -> None:
    written = appliance.export_deployment_files(tmp_path / "deploy")
    by_name = {path.name: path for path in written}
    assert set(by_name) == set(appliance.DEPLOYMENT_FILES)

    service = by_name["openorchestrion.service"].read_text()
    assert "ExecStart=/opt/openorchestrion/venv/bin/openorchestrion-serve" in service
    assert "EnvironmentFile=-/etc/openorchestrion/openorchestrion.env" in service
    assert "WorkingDirectory=/var/lib/openorchestrion" in service
    assert "Restart=on-failure" in service
    assert "PrivateDevices" not in service  # MIDI devices must remain visible.

    discovery = by_name["openorchestrion-discovery.service"].read_text()
    assert "Environment=OPENORCHESTRION_PORT=8000" in discovery
    assert "EnvironmentFile=-/etc/openorchestrion/openorchestrion.env" in discovery
    assert "avahi-publish-service" in discovery
    assert "${OPENORCHESTRION_PORT}" in discovery
    assert "_http._tcp" in discovery
    assert "PartOf=openorchestrion.service" in discovery
    assert "Requires=openorchestrion.service" not in discovery

    environment = by_name["openorchestrion.env"].read_text()
    assert "OPENORCHESTRION_LIBRARY_ROOT=/var/lib/openorchestrion/library" in environment
    assert "OPENORCHESTRION_VIRTUAL_MIDI=0" in environment

    desktop = by_name["openorchestrion-kiosk.desktop"].read_text()
    assert "openorchestrion-kiosk" in desktop
    assert "openorchestrion-serve" not in desktop

    installer = by_name["install-appliance.sh"]
    assert installer.stat().st_mode & 0o111
    text = installer.read_text()
    assert "preserving existing" in text
    assert "systemctl stop openorchestrion.service" in text
    assert "systemctl restart openorchestrion.service" in text
    assert "rm -rf /var/lib/openorchestrion" not in text


def test_discovery_installer_is_explicit_about_hostname_and_optional_avahi(tmp_path: Path) -> None:
    files = {path.name: path for path in appliance.export_deployment_files(tmp_path / "deploy")}
    installer = files["install-appliance.sh"]
    text = installer.read_text()

    syntax = subprocess.run(["sh", "-n", str(installer)], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr

    assert "--hostname NAME" in text
    assert "APPLIANCE_HOSTNAME=" in text
    assert 'if [ -n "$APPLIANCE_HOSTNAME" ]; then' in text
    assert 'hostnamectl set-hostname "$APPLIANCE_HOSTNAME"' in text
    assert "never changed unless" in text

    assert "command -v avahi-publish-service" in text
    assert "openorchestrion-discovery.service" in text
    assert "warning: Avahi discovery unavailable" in text
    assert "systemctl restart openorchestrion.service" in text


def test_reference_environment_uses_absolute_durable_paths(tmp_path: Path) -> None:
    settings = Settings(
        library_root=tmp_path / "state" / "library",
        catalog_db=tmp_path / "state" / "library" / "catalog.db",
        history_db=tmp_path / "state" / "history.db",
    )
    settings.library_root.mkdir(parents=True)
    assert appliance.validate_durable_paths(settings) == []


def test_smoke_checks_health_web_manifest_and_durable_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "state" / "library"
    root.mkdir(parents=True)
    settings = Settings(
        library_root=root,
        catalog_db=root / "catalog.db",
        history_db=tmp_path / "state" / "history.db",
    )

    def fake_request(url: str, *, timeout: float = 3.0) -> tuple[int, bytes, str]:
        del timeout
        if url.endswith("/api/health"):
            return 200, json.dumps({"status": "ok"}).encode(), "application/json"
        if url.endswith("/manifest.webmanifest"):
            return 200, json.dumps({"name": "OpenOrchestrion"}).encode(), "application/manifest+json"
        return 200, b"<!doctype html><html><body>OpenOrchestrion</body></html>", "text/html"

    monkeypatch.setattr(appliance, "_request", fake_request)
    result = appliance.smoke("http://127.0.0.1:8000/", settings=settings)
    assert result["ok"] is True
    assert result["health"] == {"status": "ok"}
    assert result["manifest_name"] == "OpenOrchestrion"


def test_smoke_reports_relative_or_missing_durable_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        library_root=Path("relative/library"),
        catalog_db=Path("relative/library/catalog.db"),
        history_db=Path("relative/history.db"),
    )

    def fake_request(url: str, *, timeout: float = 3.0) -> tuple[int, bytes, str]:
        del timeout
        if url.endswith("/api/health"):
            return 200, b'{"status":"ok"}', "application/json"
        if url.endswith("/manifest.webmanifest"):
            return 200, b'{"name":"OpenOrchestrion"}', "application/manifest+json"
        return 200, b"<html></html>", "text/html"

    monkeypatch.setattr(appliance, "_request", fake_request)
    result = appliance.smoke("http://127.0.0.1:8000", settings=settings)
    assert result["ok"] is False
    assert any("not absolute" in error for error in result["errors"])
