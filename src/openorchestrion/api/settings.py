from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIBRARY_ROOT = "var/library"


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem locations the API reads.

    Resolved once at startup so request handlers never consult the environment.
    """

    library_root: Path
    catalog_db: Path
    history_db: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        root = Path(env.get("OPENORCHESTRION_LIBRARY_ROOT", DEFAULT_LIBRARY_ROOT))
        return cls(
            library_root=root,
            catalog_db=Path(env.get("OPENORCHESTRION_CATALOG_DB", str(root / "catalog.db"))),
            history_db=Path(env.get("OPENORCHESTRION_HISTORY_DB", str(root / "history.db"))),
        )
