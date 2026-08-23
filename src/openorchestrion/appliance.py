"""Production runtime helpers for the Raspberry Pi appliance.

The application remains one FastAPI process with server-owned playback. This
module only supplies production launch, kiosk, deployment-template export, and
post-install smoke commands around that existing application.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .api.settings import Settings

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
DEFAULT_ENV_FILE = Path("/etc/openorchestrion/openorchestrion.env")
DEPLOYMENT_FILES = (
    "openorchestrion.service",
    "openorchestrion.env",
    "openorchestrion-kiosk.desktop",
    "install-appliance.sh",
)


@dataclass(frozen=True, slots=True)
class ServerOptions:
    host: str
    port: int
    log_level: str


def _unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def load_appliance_environment(
    environ: Mapping[str, str] | None = None,
    *,
    config_path: str | Path | None = None,
) -> dict[str, str]:
    """Load the systemd-style appliance env file, then apply process overrides.

    systemd loads ``/etc/openorchestrion/openorchestrion.env`` for the backend,
    but a desktop kiosk process and an administrator's smoke command do not
    inherit that service environment. Reading the same simple ``KEY=value``
    file here keeps all three entry points on one configuration.
    """
    process = dict(os.environ if environ is None else environ)
    configured = config_path or process.get("OPENORCHESTRION_ENV_FILE") or DEFAULT_ENV_FILE
    path = Path(configured)
    merged: dict[str, str] = {}
    if path.is_file():
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise ValueError(f"{path}:{number}: expected KEY=value")
            key, value = line.split("=", 1)
            key = key.strip()
            if not key:
                raise ValueError(f"{path}:{number}: empty environment key")
            merged[key] = _unquote(value)
    merged.update(process)
    return merged


def server_options(environ: Mapping[str, str] | None = None) -> ServerOptions:
    env = load_appliance_environment(environ)
    host = env.get("OPENORCHESTRION_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST
    try:
        port = int(env.get("OPENORCHESTRION_PORT", str(DEFAULT_PORT)))
    except ValueError as exc:
        raise ValueError("OPENORCHESTRION_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("OPENORCHESTRION_PORT must be between 1 and 65535")
    log_level = env.get("OPENORCHESTRION_LOG_LEVEL", "info").strip().lower() or "info"
    return ServerOptions(host=host, port=port, log_level=log_level)


def serve_main() -> None:
    """Run the single production FastAPI process.

    Multiple Uvicorn workers are intentionally not exposed: queue, playback,
    MIDI ports, and WebSocket sequence state are server-owned and must live in
    one process on the appliance.
    """
    import uvicorn

    env = load_appliance_environment()
    # Uvicorn imports ``openorchestrion.app:app`` after this function starts.
    # Populate values from the shared env file so Settings.from_env() inside the
    # FastAPI lifespan sees the same paths even when serve_main is launched
    # manually rather than by systemd. Existing process variables already won
    # during load_appliance_environment and are therefore preserved here.
    for key, value in env.items():
        os.environ[key] = value

    options = server_options(env)
    uvicorn.run(
        "openorchestrion.app:app",
        host=options.host,
        port=options.port,
        log_level=options.log_level,
        workers=1,
        reload=False,
    )


def _request(url: str, *, timeout: float = 3.0) -> tuple[int, bytes, str]:
    request = Request(url, headers={"User-Agent": "OpenOrchestrion-Smoke/1"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - operator-controlled URL
        return response.status, response.read(), response.headers.get_content_type()


def _base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _kiosk_url(environ: Mapping[str, str]) -> str:
    explicit = environ.get("OPENORCHESTRION_KIOSK_URL")
    if explicit:
        return _base_url(explicit)
    port = server_options(environ).port
    return f"http://127.0.0.1:{port}"


def wait_for_health(url: str, *, timeout_seconds: float = 60.0) -> None:
    """Wait for the local service without making boot depend on the Internet."""
    base = _base_url(url)
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, payload, _ = _request(f"{base}/api/health", timeout=1.5)
            if status == 200 and json.loads(payload).get("status") == "ok":
                return
        except (OSError, HTTPError, URLError, ValueError, json.JSONDecodeError) as exc:
            last_error = exc
        time.sleep(0.5)
    detail = f": {last_error}" if last_error else ""
    raise RuntimeError(f"OpenOrchestrion did not become healthy within {timeout_seconds:g}s{detail}")


def _find_chromium(environ: Mapping[str, str]) -> str:
    explicit = environ.get("OPENORCHESTRION_CHROMIUM")
    if explicit:
        resolved = shutil.which(explicit) if os.sep not in explicit else explicit
        if resolved and Path(resolved).is_file():
            return resolved
        raise RuntimeError(f"configured Chromium executable does not exist: {explicit}")
    for candidate in ("chromium", "chromium-browser"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("Chromium is not installed (expected chromium or chromium-browser)")


def kiosk_main() -> None:
    """Wait for the local service, then replace this process with Chromium kiosk."""
    try:
        env = load_appliance_environment()
        url = _kiosk_url(env)
        timeout = float(env.get("OPENORCHESTRION_KIOSK_TIMEOUT", "60"))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if timeout <= 0:
        raise SystemExit("OPENORCHESTRION_KIOSK_TIMEOUT must be positive")

    try:
        wait_for_health(url, timeout_seconds=timeout)
        chromium = _find_chromium(env)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from None

    profile = Path.home() / ".local" / "share" / "openorchestrion" / "chromium"
    profile.mkdir(parents=True, exist_ok=True)
    argv = [
        chromium,
        "--kiosk",
        "--no-first-run",
        "--noerrdialogs",
        "--disable-session-crashed-bubble",
        "--disable-features=Translate,MediaRouter",
        f"--user-data-dir={profile}",
        url,
    ]
    os.execv(chromium, argv)


def export_deployment_files(destination: str | Path) -> tuple[Path, ...]:
    """Export the wheel-shipped reference deployment files to a normal directory."""
    target = Path(destination)
    target.mkdir(parents=True, exist_ok=True)
    resources = files("openorchestrion.deployment")
    written: list[Path] = []
    for name in DEPLOYMENT_FILES:
        output = target / name
        output.write_bytes(resources.joinpath(name).read_bytes())
        if name.endswith(".sh"):
            output.chmod(0o755)
        written.append(output)
    return tuple(written)


def deploy_main() -> None:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-deploy",
        description="Export the deployment files shipped inside the installed wheel.",
    )
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    for path in export_deployment_files(args.output_dir):
        print(path)


def validate_durable_paths(settings: Settings) -> list[str]:
    """Return deployment-path problems without requiring catalog/history to exist yet."""
    errors: list[str] = []
    values = {
        "library_root": settings.library_root,
        "catalog_db": settings.catalog_db,
        "history_db": settings.history_db,
    }
    for label, path in values.items():
        if not path.is_absolute():
            errors.append(f"{label} is not absolute: {path}")
    if not settings.library_root.is_dir():
        errors.append(f"library_root does not exist: {settings.library_root}")
    for label, path in (("catalog_db", settings.catalog_db), ("history_db", settings.history_db)):
        if not path.parent.is_dir():
            errors.append(f"{label} parent does not exist: {path.parent}")
    return errors


def smoke(url: str, *, settings: Settings | None = None) -> dict[str, Any]:
    """Verify HTTP health, packaged web assets, and configured durable paths."""
    base = _base_url(url)
    active_settings = settings or Settings.from_env(load_appliance_environment())
    errors = validate_durable_paths(active_settings)
    checks: dict[str, Any] = {
        "url": base,
        "library_root": str(active_settings.library_root),
        "catalog_db": str(active_settings.catalog_db),
        "history_db": str(active_settings.history_db),
    }

    try:
        status, payload, _ = _request(f"{base}/api/health")
        health = json.loads(payload)
        checks["health"] = health
        if status != 200 or health.get("status") != "ok":
            errors.append("/api/health did not return status=ok")
    except Exception as exc:  # noqa: BLE001 - smoke should report every failure together
        errors.append(f"health request failed: {type(exc).__name__}: {exc}")

    try:
        status, payload, content_type = _request(f"{base}/")
        text = payload.decode("utf-8", errors="replace").lower()
        checks["web_content_type"] = content_type
        if status != 200 or "<html" not in text:
            errors.append("web application shell was not served at /")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"web request failed: {type(exc).__name__}: {exc}")

    try:
        status, payload, _ = _request(f"{base}/manifest.webmanifest")
        manifest = json.loads(payload)
        checks["manifest_name"] = manifest.get("name")
        if status != 200 or not manifest.get("name"):
            errors.append("manifest.webmanifest is missing or invalid")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"manifest request failed: {type(exc).__name__}: {exc}")

    checks["ok"] = not errors
    checks["errors"] = errors
    return checks


def smoke_main() -> None:
    try:
        env = load_appliance_environment()
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    parser = argparse.ArgumentParser(prog="openorchestrion-smoke")
    parser.add_argument("--url", default=_kiosk_url(env))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = smoke(args.url, settings=Settings.from_env(env))
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        state = "ok" if result["ok"] else "FAILED"
        print(f"OpenOrchestrion smoke: {state}")
        print(f"  service: {result['url']}")
        print(f"  library: {result['library_root']}")
        for error in result["errors"]:
            print(f"  error: {error}")
    if not result["ok"]:
        raise SystemExit(1)
