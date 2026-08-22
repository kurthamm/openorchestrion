from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIBRARY_ROOT = "var/library"


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem locations and hardware-free development settings."""

    library_root: Path
    catalog_db: Path
    history_db: Path
    virtual_midi: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        root = Path(env.get("OPENORCHESTRION_LIBRARY_ROOT", DEFAULT_LIBRARY_ROOT))
        return cls(
            library_root=root,
            catalog_db=Path(env.get("OPENORCHESTRION_CATALOG_DB", str(root / "catalog.db"))),
            history_db=Path(env.get("OPENORCHESTRION_HISTORY_DB", str(root / "history.db"))),
            virtual_midi=_env_bool(env.get("OPENORCHESTRION_VIRTUAL_MIDI")),
        )
