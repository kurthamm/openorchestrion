"""Durable, non-security state for the first-run setup wizard."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

SETUP_VERSION = 1
SETUP_FILENAME = "setup.json"


@dataclass(frozen=True, slots=True)
class SetupProgress:
    version: int
    complete: bool
    completed_at: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "complete": self.complete,
            "completed_at": self.completed_at,
            "reason": self.reason,
        }


def setup_path(state_root: str | Path) -> Path:
    return Path(state_root) / SETUP_FILENAME


def read_setup_progress(path: str | Path) -> SetupProgress:
    marker = Path(path)
    if not marker.exists():
        return SetupProgress(version=SETUP_VERSION, complete=False, reason="not_completed")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return SetupProgress(version=SETUP_VERSION, complete=False, reason="marker_unreadable")
    if not isinstance(payload, dict):
        return SetupProgress(version=SETUP_VERSION, complete=False, reason="marker_invalid")
    try:
        version = int(payload.get("version", 0))
    except (TypeError, ValueError):
        return SetupProgress(version=SETUP_VERSION, complete=False, reason="marker_invalid")
    completed_at = payload.get("completed_at")
    if completed_at is not None and not isinstance(completed_at, str):
        return SetupProgress(version=SETUP_VERSION, complete=False, reason="marker_invalid")
    if version != SETUP_VERSION:
        return SetupProgress(
            version=SETUP_VERSION,
            complete=False,
            completed_at=completed_at,
            reason="wizard_version_changed",
        )
    return SetupProgress(
        version=SETUP_VERSION,
        complete=True,
        completed_at=completed_at,
        reason=None,
    )


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
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


def mark_setup_complete(path: str | Path) -> SetupProgress:
    completed_at = datetime.now(UTC).isoformat()
    marker = Path(path)
    _atomic_json(marker, {"version": SETUP_VERSION, "completed_at": completed_at})
    return SetupProgress(
        version=SETUP_VERSION,
        complete=True,
        completed_at=completed_at,
        reason=None,
    )


def reset_setup(path: str | Path) -> SetupProgress:
    marker = Path(path)
    marker.unlink(missing_ok=True)
    return SetupProgress(version=SETUP_VERSION, complete=False, reason="not_completed")


__all__ = [
    "SETUP_FILENAME",
    "SETUP_VERSION",
    "SetupProgress",
    "mark_setup_complete",
    "read_setup_progress",
    "reset_setup",
    "setup_path",
]
