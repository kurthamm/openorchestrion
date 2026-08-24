"""Privileged local configuration for an installed OpenOrchestrion appliance.

The web application is intentionally not a system configuration surface. The
reference service is reachable from the household LAN and has no authentication,
so API keys and `/etc` writes belong in a command an administrator runs *on the
Pi*. This module edits the two existing systemd EnvironmentFile documents while
preserving comments and future/unknown keys.
"""

from __future__ import annotations

import argparse
import getpass
import grp
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .api.settings import Settings

DEFAULT_ENV_FILE = Path("/etc/openorchestrion/openorchestrion.env")
DEFAULT_SECRETS_FILE = Path("/etc/openorchestrion/openorchestrion.secrets.env")
DEFAULT_SERVICE = "openorchestrion.service"
_ASSIGNMENT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


class ConfigurationError(ValueError):
    """A configuration request that must not alter the current installation."""


@dataclass(frozen=True, slots=True)
class EnvironmentDocument:
    """A systemd-style EnvironmentFile with its comments/order preserved."""

    path: Path
    lines: tuple[str, ...]

    @classmethod
    def read(cls, path: str | Path) -> "EnvironmentDocument":
        target = Path(path)
        if not target.exists():
            return cls(target, ())
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigurationError(f"cannot read {target}: {exc}") from exc
        return cls(target, tuple(text.splitlines()))

    def values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for number, raw in enumerate(self.lines, start=1):
            line = raw.strip()
            if not line or line.startswith(("#", ";")):
                continue
            if "=" not in line:
                raise ConfigurationError(f"{self.path}:{number}: expected KEY=value")
            key, value = line.split("=", 1)
            key = key.strip()
            if not _ASSIGNMENT.match(f"{key}="):
                raise ConfigurationError(f"{self.path}:{number}: invalid environment key {key!r}")
            result[key] = _unquote(value)
        return result

    def updated(self, changes: Mapping[str, str | None]) -> str:
        """Render changes without discarding comments, order, or unknown keys.

        ``None`` removes a key. New keys are appended at the end in the order
        supplied by the caller. Values are deliberately restricted to one line;
        the appliance settings do not need shell expansion or multiline secrets.
        """
        normalized: dict[str, str | None] = {}
        for key, value in changes.items():
            if not _ASSIGNMENT.match(f"{key}="):
                raise ConfigurationError(f"invalid environment key {key!r}")
            if value is not None:
                value = str(value)
                if "\n" in value or "\r" in value:
                    raise ConfigurationError(f"{key} may not contain a newline")
            normalized[key] = value

        seen: set[str] = set()
        rendered: list[str] = []
        for raw in self.lines:
            match = _ASSIGNMENT.match(raw)
            if not match:
                rendered.append(raw)
                continue
            key = match.group(1)
            if key not in normalized:
                rendered.append(raw)
                continue
            seen.add(key)
            value = normalized[key]
            if value is not None:
                rendered.append(f"{key}={_quote(value)}")

        if rendered and rendered[-1] != "":
            rendered.append("")
        for key, value in normalized.items():
            if key in seen or value is None:
                continue
            rendered.append(f"{key}={_quote(value)}")
        return "\n".join(rendered).rstrip("\n") + "\n"


def _unquote(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _quote(value: str) -> str:
    # systemd EnvironmentFile accepts quoted values. Keep ordinary tokens plain
    # for readability and quote only when whitespace/comment syntax would make
    # the line ambiguous. Quotes/backslashes are escaped conservatively.
    if value and not any(char.isspace() for char in value) and not value.startswith(("#", ";")):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _atomic_write(path: Path, content: str, *, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    previous = path.stat() if path.exists() else None
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, previous.st_mode & 0o777 if previous else mode)
        if previous is not None:
            try:
                os.chown(temporary, previous.st_uid, previous.st_gid)
            except PermissionError:
                pass
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _reference_permissions(path: Path, *, secret: bool) -> None:
    """Apply the reference installation ownership only to the real `/etc` files."""
    expected = DEFAULT_SECRETS_FILE if secret else DEFAULT_ENV_FILE
    if path != expected or os.geteuid() != 0:
        return
    mode = 0o640 if secret else 0o644
    os.chmod(path, mode)
    if secret:
        try:
            group = grp.getgrnam("openorchestrion")
        except KeyError as exc:
            raise ConfigurationError("service group 'openorchestrion' does not exist") from exc
        os.chown(path, 0, group.gr_gid)
    else:
        os.chown(path, 0, 0)


def _requires_privilege(path: Path) -> bool:
    try:
        return path.is_relative_to(Path("/etc"))
    except AttributeError:  # pragma: no cover - Python 3.11 always has is_relative_to
        return str(path).startswith("/etc/")


def _validate_candidate(
    current: Mapping[str, str],
    changes: Mapping[str, str | None],
) -> None:
    merged = dict(current)
    for key, value in changes.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    # Settings is intentionally non-secret. This validates every application
    # setting this command is allowed to change before the file is replaced.
    Settings.from_env(merged)


def configure_files(
    *,
    env_path: str | Path,
    secrets_path: str | Path,
    env_changes: Mapping[str, str | None],
    secret_changes: Mapping[str, str | None],
) -> bool:
    """Validate and atomically apply a local configuration transaction.

    Validation happens for both documents first. If it fails, neither file is
    touched. Once validation succeeds, each EnvironmentFile is replaced
    atomically. The reference secrets file is kept service-only (0640).
    """
    env_file = Path(env_path)
    secrets_file = Path(secrets_path)
    if os.geteuid() != 0 and any(_requires_privilege(path) for path in (env_file, secrets_file)):
        raise ConfigurationError("writing the reference /etc configuration requires root (sudo)")

    env_document = EnvironmentDocument.read(env_file)
    secret_document = EnvironmentDocument.read(secrets_file)
    current_env = env_document.values()
    # Parse secrets too so malformed existing data is not silently overwritten.
    secret_document.values()
    _validate_candidate(current_env, env_changes)

    env_content = env_document.updated(env_changes)
    secret_content = secret_document.updated(secret_changes)
    env_previous = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    secret_previous = secrets_file.read_text(encoding="utf-8") if secrets_file.exists() else ""
    env_changed = bool(env_changes) and env_content != env_previous
    secret_changed = bool(secret_changes) and secret_content != secret_previous

    if env_changed:
        _atomic_write(env_file, env_content, mode=0o644)
        _reference_permissions(env_file, secret=False)
    if secret_changed:
        _atomic_write(secrets_file, secret_content, mode=0o640)
        _reference_permissions(secrets_file, secret=True)
    return env_changed or secret_changed


def _redacted(values: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        if any(marker in key.upper() for marker in _SECRET_MARKERS):
            result[key] = "<configured>" if value else "<empty>"
        else:
            result[key] = value
    return result


def show_configuration(
    env_path: str | Path = DEFAULT_ENV_FILE,
    secrets_path: str | Path = DEFAULT_SECRETS_FILE,
) -> dict[str, str]:
    values = EnvironmentDocument.read(env_path).values()
    try:
        secrets = EnvironmentDocument.read(secrets_path).values()
    except ConfigurationError:
        secrets = {}
    values.update(_redacted(secrets))
    return _redacted(values)


def _restart_service(service: str) -> None:
    try:
        subprocess.run(["systemctl", "restart", service], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ConfigurationError(f"configuration was written but {service} could not restart: {exc}") from exc


def _read_key_file(path: str) -> str:
    try:
        value = Path(path).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigurationError(f"cannot read API-key file {path}: {exc}") from exc
    if not value:
        raise ConfigurationError("API-key file is empty")
    if "\n" in value or "\r" in value:
        raise ConfigurationError("API-key file must contain exactly one line")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-configure",
        description="Safely configure an installed OpenOrchestrion appliance on the local Pi.",
    )
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE))
    parser.add_argument("--secrets-file", default=str(DEFAULT_SECRETS_FILE))
    parser.add_argument("--show", action="store_true", help="Show effective config with secrets redacted")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--ai-provider", choices=("openai", "off"))
    parser.add_argument("--ai-model")
    parser.add_argument("--ai-timeout", type=float)
    parser.add_argument("--virtual-midi", choices=("on", "off"))
    key = parser.add_mutually_exclusive_group()
    key.add_argument(
        "--set-openai-key",
        action="store_true",
        help="Prompt for OPENAI_API_KEY with terminal echo disabled",
    )
    key.add_argument(
        "--openai-key-file",
        metavar="PATH",
        help="Read OPENAI_API_KEY from a one-line file (for local automation)",
    )
    key.add_argument("--clear-openai-key", action="store_true")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--service", default=DEFAULT_SERVICE)
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    env_path = Path(args.env_file)
    secrets_path = Path(args.secrets_file)

    if args.show:
        try:
            values = show_configuration(env_path, secrets_path)
        except ConfigurationError as exc:
            parser.error(str(exc))
        if args.json:
            print(json.dumps(values, indent=2, sort_keys=True))
        else:
            for key, value in sorted(values.items()):
                print(f"{key}={value}")
        return

    env_changes: dict[str, str | None] = {}
    secret_changes: dict[str, str | None] = {}
    if args.ai_provider is not None:
        env_changes["OPENORCHESTRION_AI_PROVIDER"] = args.ai_provider
    if args.ai_model is not None:
        env_changes["OPENORCHESTRION_AI_MODEL"] = args.ai_model
    if args.ai_timeout is not None:
        if args.ai_timeout <= 0:
            parser.error("--ai-timeout must be positive")
        env_changes["OPENORCHESTRION_AI_TIMEOUT_SECONDS"] = str(args.ai_timeout)
    if args.virtual_midi is not None:
        env_changes["OPENORCHESTRION_VIRTUAL_MIDI"] = "1" if args.virtual_midi == "on" else "0"

    if args.set_openai_key:
        value = getpass.getpass("OpenAI API key: ").strip()
        if not value:
            parser.error("API key cannot be empty")
        secret_changes["OPENAI_API_KEY"] = value
    elif args.openai_key_file:
        try:
            secret_changes["OPENAI_API_KEY"] = _read_key_file(args.openai_key_file)
        except ConfigurationError as exc:
            parser.error(str(exc))
    elif args.clear_openai_key:
        secret_changes["OPENAI_API_KEY"] = None

    if not env_changes and not secret_changes:
        parser.error("nothing to change; pass a setting or --show")

    try:
        changed = configure_files(
            env_path=env_path,
            secrets_path=secrets_path,
            env_changes=env_changes,
            secret_changes=secret_changes,
        )
        if changed and not args.no_restart:
            _restart_service(args.service)
    except ConfigurationError as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        raise SystemExit(2) from None

    print("configuration updated" if changed else "configuration already matched requested values")
    if changed and args.no_restart:
        print("service not restarted (--no-restart)")


__all__ = [
    "ConfigurationError",
    "DEFAULT_ENV_FILE",
    "DEFAULT_SECRETS_FILE",
    "EnvironmentDocument",
    "configure_files",
    "show_configuration",
]


if __name__ == "__main__":
    main()
