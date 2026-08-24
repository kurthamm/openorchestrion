"""Privileged operator workflow around the verified backup/restore core.

The household HTTP service is intentionally unauthenticated on the trusted LAN,
so destructive restore/replacement is a local administrator operation. This
module supplies the packaged CLI and service/swap orchestration without creating
a second archive format.
"""

from __future__ import annotations

import argparse
import grp
import json
import os
import pwd
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .appliance import load_appliance_environment, server_options, wait_for_health
from .backup import BackupError, RestoreReport, create_backup, restore_backup

REFERENCE_STATE_ROOT = Path("/var/lib/openorchestrion")
DEFAULT_SERVICE = "openorchestrion.service"
SERVICE_USER = "openorchestrion"
SERVICE_GROUP = "openorchestrion"


class OperatorError(RuntimeError):
    """A privileged backup/recovery operation could not complete safely."""


@dataclass(frozen=True, slots=True)
class InspectReport:
    archive: str
    asset_count: int
    file_count: int
    history_included: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReplacementReport:
    archive: str
    state_root: str
    asset_count: int
    history_restored: bool
    rollback_archive: str | None
    service_managed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _absolute(value: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(Path(value).expanduser())))


def _is_reference_root(path: Path) -> bool:
    return path == REFERENCE_STATE_ROOT


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _require_reference_privilege(path: Path) -> None:
    if _is_reference_root(path) and os.geteuid() != 0:
        raise OperatorError(f"operating on {REFERENCE_STATE_ROOT} requires root (sudo)")


def _systemctl(action: str, service: str) -> None:
    try:
        subprocess.run(["systemctl", action, service], check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OperatorError(f"systemctl {action} {service} failed: {exc}") from exc


def _stop_service(service: str) -> None:
    _systemctl("stop", service)


def _start_service(service: str) -> None:
    _systemctl("start", service)


def _reference_health_url() -> str:
    env = load_appliance_environment()
    return f"http://127.0.0.1:{server_options(env).port}"


def _wait_service_health(url: str, *, timeout_seconds: float) -> None:
    try:
        wait_for_health(url, timeout_seconds=timeout_seconds)
    except Exception as exc:  # health implementation already provides useful detail
        raise OperatorError(f"restored appliance did not become healthy: {exc}") from exc


def _state_has_durable_payload(root: Path) -> bool:
    """Distinguish a fresh installer skeleton from state worth protecting.

    `setup.json`, an ordinary rebuildable catalog, empty directories and
    permanent sidecar lock files are not irreplaceable. MIDI objects/sidecars,
    history, symlinks, or anything unexpected are treated conservatively as
    durable state.
    """
    if root.is_symlink():
        return True
    if not root.exists():
        return False
    if not root.is_dir():
        return True

    for entry in root.iterdir():
        if entry.name == "setup.json" and entry.is_file() and not entry.is_symlink():
            continue
        if entry.name == "history.db":
            return True
        if entry.name != "library" or entry.is_symlink() or not entry.is_dir():
            return True

        for library_entry in entry.iterdir():
            if (
                library_entry.name == "catalog.db"
                and library_entry.is_file()
                and not library_entry.is_symlink()
            ):
                continue
            if library_entry.name != "assets" or library_entry.is_symlink() or not library_entry.is_dir():
                return True
            for asset in library_entry.iterdir():
                if asset.name.endswith(".json.lock") and asset.is_file() and not asset.is_symlink():
                    continue
                return True
    return False


def _rollback_archive_path(state_root: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return state_root.parent / f"{state_root.name}-rollback-{stamp}-{uuid4().hex[:8]}.zip"


def _apply_reference_state_permissions(root: Path) -> None:
    """Make a verified reference-state tree writable only by the service account.

    The caller decides whether the final target is the reference state root. The
    tree passed here is normally the sibling preflight candidate, so it must not
    require ``root == REFERENCE_STATE_ROOT`` itself.
    """
    try:
        uid = pwd.getpwnam(SERVICE_USER).pw_uid
        gid = grp.getgrnam(SERVICE_GROUP).gr_gid
    except KeyError as exc:
        raise OperatorError("reference service user/group does not exist") from exc

    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if current_path.is_symlink():
            raise OperatorError(f"restored state unexpectedly contains symlink: {current_path}")
        os.chown(current_path, uid, gid)
        os.chmod(current_path, 0o750)
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                raise OperatorError(f"restored state unexpectedly contains symlink: {path}")
        for name in files:
            path = current_path / name
            if path.is_symlink():
                raise OperatorError(f"restored state unexpectedly contains symlink: {path}")
            os.chown(path, uid, gid)
            os.chmod(path, 0o640)


def inspect_backup(archive: str | Path) -> InspectReport:
    """Fully verify a backup without publishing it over application state."""
    source = _absolute(archive)
    with tempfile.TemporaryDirectory(prefix="openorchestrion-inspect-") as parent_name:
        candidate = Path(parent_name) / "state"
        report = restore_backup(source, candidate)
        return InspectReport(
            archive=str(source),
            asset_count=report.asset_count,
            file_count=report.file_count,
            history_included=report.history_restored,
        )


def _preflight_candidate(archive: Path, state_root: Path) -> tuple[Path, RestoreReport]:
    candidate = state_root.parent / f".{state_root.name}.candidate.{uuid4().hex}"
    try:
        report = restore_backup(archive, candidate)
    except Exception:
        shutil.rmtree(candidate, ignore_errors=True)
        raise
    return candidate, report


def _swap_in(candidate: Path, target: Path, previous: Path) -> bool:
    """Publish candidate; return whether an old tree was moved aside."""
    moved_old = False
    try:
        if target.exists():
            if target.is_symlink() or not target.is_dir():
                raise OperatorError(f"state root is not a regular directory: {target}")
            os.replace(target, previous)
            moved_old = True
        os.replace(candidate, target)
        return moved_old
    except BaseException:
        if moved_old and previous.exists() and not target.exists():
            os.replace(previous, target)
        raise


def _rollback_swap(target: Path, previous: Path, failed: Path) -> bool:
    """Move the failed new tree aside and restore the old tree when one existed."""
    if target.exists():
        os.replace(target, failed)
    if previous.exists():
        os.replace(previous, target)
        return True
    return False


def _prepare_replacement(
    source: Path,
    target: Path,
    *,
    durable: bool,
    rollback_archive: str | Path | None,
) -> tuple[Path, RestoreReport, Path | None]:
    """Do every fallible preparation while the live service/state are untouched."""
    if _is_within(source, target):
        raise OperatorError("restore archive must live outside the state root being replaced")

    candidate, verified = _preflight_candidate(source, target)
    rollback_path: Path | None = None
    try:
        if durable:
            rollback_path = (
                _absolute(rollback_archive)
                if rollback_archive is not None
                else _rollback_archive_path(target)
            )
            if _is_within(rollback_path, target):
                raise OperatorError("rollback archive must live outside the state root being replaced")
            if rollback_path == source:
                raise OperatorError("rollback archive may not overwrite the restore source archive")
            create_backup(target, rollback_path)

        if _is_reference_root(target):
            _apply_reference_state_permissions(candidate)
        return candidate, verified, rollback_path
    except BaseException:
        shutil.rmtree(candidate, ignore_errors=True)
        raise


def replace_from_backup(
    archive: str | Path,
    state_root: str | Path = REFERENCE_STATE_ROOT,
    *,
    replace_existing: bool = False,
    rollback_archive: str | Path | None = None,
    service: str = DEFAULT_SERVICE,
    manage_service: bool = True,
    health_url: str | None = None,
    health_timeout_seconds: float = 60.0,
) -> ReplacementReport:
    """Preflight, protect, atomically swap, health-check, and rollback on failure."""
    source = _absolute(archive)
    target = _absolute(state_root)
    _require_reference_privilege(target)
    if target.is_symlink():
        raise OperatorError(f"state root may not be a symlink: {target}")
    if manage_service and os.geteuid() != 0:
        raise OperatorError("service-controlled restore requires root (sudo)")
    if not manage_service and _is_reference_root(target):
        raise OperatorError("reference state restore may not disable service control")

    durable = _state_has_durable_payload(target)
    if durable and not replace_existing:
        raise OperatorError("existing durable state found; pass --replace-existing to replace it")

    # Archive verification, rollback backup creation and candidate permission
    # preparation all happen before the service is stopped. A failure here never
    # enters the destructive rollback phase and never interrupts playback.
    candidate, verified, rollback_path = _prepare_replacement(
        source,
        target,
        durable=durable,
        rollback_archive=rollback_archive,
    )

    previous = target.parent / f".{target.name}.previous.{uuid4().hex}"
    failed = target.parent / f".{target.name}.failed.{uuid4().hex}"
    moved_old = False
    service_stopped = False
    new_tree_live = False

    try:
        if manage_service:
            _stop_service(service)
            service_stopped = True

        moved_old = _swap_in(candidate, target, previous)
        new_tree_live = True

        if manage_service:
            _start_service(service)
            service_stopped = False
            check_url = health_url or _reference_health_url()
            _wait_service_health(check_url, timeout_seconds=health_timeout_seconds)

        if moved_old:
            shutil.rmtree(previous)
        return ReplacementReport(
            archive=str(source),
            state_root=str(target),
            asset_count=verified.asset_count,
            history_restored=verified.history_restored,
            rollback_archive=str(rollback_path) if rollback_path is not None else None,
            service_managed=manage_service,
        )
    except BaseException as exc:
        if new_tree_live and manage_service and not service_stopped:
            try:
                _stop_service(service)
                service_stopped = True
            except OperatorError as stop_exc:
                raise OperatorError(
                    f"restore failed ({exc}) and the new service could not be stopped safely "
                    f"({stop_exc}); filesystem rollback was not attempted; "
                    f"previous_tree={previous if previous.exists() else None}; "
                    f"rollback_archive={rollback_path}"
                ) from exc

        original_restored = False
        if new_tree_live:
            try:
                original_restored = _rollback_swap(target, previous, failed)
            except BaseException as rollback_exc:
                raise OperatorError(
                    f"restore failed ({exc}); state-tree rollback also failed ({rollback_exc}); "
                    f"rollback archive={rollback_path}"
                ) from exc

        if manage_service and original_restored:
            try:
                _start_service(service)
                service_stopped = False
                check_url = health_url or _reference_health_url()
                _wait_service_health(check_url, timeout_seconds=health_timeout_seconds)
            except BaseException as rollback_health_exc:
                raise OperatorError(
                    f"restore failed ({exc}); original state was restored but did not become "
                    f"healthy ({rollback_health_exc}); failed restored tree={failed if failed.exists() else None}; "
                    f"rollback archive={rollback_path}"
                ) from exc

        if original_restored:
            if failed.exists():
                shutil.rmtree(failed, ignore_errors=True)
            raise OperatorError(f"restore failed and original state was restored: {exc}") from exc

        # There was no prior state tree to restore. Preserve the failed candidate
        # for diagnosis rather than claiming a rollback that did not exist.
        failed_path = failed if failed.exists() else None
        raise OperatorError(
            f"restore failed and there was no previous state tree to restore: {exc}; "
            f"failed restored tree={failed_path}; rollback archive={rollback_path}"
        ) from exc
    finally:
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
        # `previous` is removed only after success or after it has been moved
        # back into place. Never blindly delete it during an uncertain rollback.


def _print_report(report: Any, *, as_json: bool) -> None:
    payload = report.to_dict()
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-backup",
        description="Create, inspect, or safely restore verified OpenOrchestrion application-data backups.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a verified application-data backup")
    create.add_argument("destination")
    create.add_argument("--state-root", default=str(REFERENCE_STATE_ROOT))
    create.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Fully verify an archive without changing live state")
    inspect.add_argument("archive")
    inspect.add_argument("--json", action="store_true")

    restore = subparsers.add_parser("restore", help="Preflight and restore application data")
    restore.add_argument("archive")
    restore.add_argument("--state-root", default=str(REFERENCE_STATE_ROOT))
    restore.add_argument("--replace-existing", action="store_true")
    restore.add_argument("--rollback-archive")
    restore.add_argument("--service", default=DEFAULT_SERVICE)
    restore.add_argument("--health-url")
    restore.add_argument("--health-timeout", type=float, default=60.0)
    restore.add_argument(
        "--no-service-control",
        action="store_true",
        help="Development/recovery only; forbidden for the reference /var/lib state root",
    )
    restore.add_argument("--json", action="store_true")
    return parser


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.command == "create":
            state_root = _absolute(args.state_root)
            destination = _absolute(args.destination)
            _require_reference_privilege(state_root)
            if _is_within(destination, state_root):
                raise OperatorError("backup destination must live outside the state root")
            report: Any = create_backup(state_root, destination)
        elif args.command == "inspect":
            report = inspect_backup(args.archive)
        else:
            if args.health_timeout <= 0:
                parser.error("--health-timeout must be positive")
            report = replace_from_backup(
                args.archive,
                args.state_root,
                replace_existing=args.replace_existing,
                rollback_archive=args.rollback_archive,
                service=args.service,
                manage_service=not args.no_service_control,
                health_url=args.health_url,
                health_timeout_seconds=args.health_timeout,
            )
        _print_report(report, as_json=args.json)
    except (BackupError, OperatorError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


__all__ = [
    "InspectReport",
    "OperatorError",
    "REFERENCE_STATE_ROOT",
    "ReplacementReport",
    "inspect_backup",
    "replace_from_backup",
]


if __name__ == "__main__":
    main()
