from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LIBRARY_ROOT = "var/library"
DEFAULT_AI_MODEL = "gpt-5.6-luna"
DEFAULT_AI_TIMEOUT_SECONDS = 15.0


def _env_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _ai_provider(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().casefold()
    if cleaned in {"", "none", "off", "disabled", "deterministic", "offline"}:
        return None
    return cleaned


def _positive_float(value: str | None, *, default: float, name: str) -> float:
    if value is None or not value.strip():
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Filesystem, MIDI, and non-secret hosted-AI settings.

    Provider credentials deliberately do not live on this object. In particular,
    ``OPENAI_API_KEY`` is read only when the configured provider is constructed,
    so repr/status/serialization of Settings cannot expose it accidentally.
    """

    library_root: Path
    catalog_db: Path
    history_db: Path
    virtual_midi: bool = False
    ai_provider: str | None = None
    ai_model: str = DEFAULT_AI_MODEL
    ai_timeout_seconds: float = DEFAULT_AI_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        root = Path(env.get("OPENORCHESTRION_LIBRARY_ROOT", DEFAULT_LIBRARY_ROOT))
        return cls(
            library_root=root,
            catalog_db=Path(env.get("OPENORCHESTRION_CATALOG_DB", str(root / "catalog.db"))),
            history_db=Path(env.get("OPENORCHESTRION_HISTORY_DB", str(root / "history.db"))),
            virtual_midi=_env_bool(env.get("OPENORCHESTRION_VIRTUAL_MIDI")),
            ai_provider=_ai_provider(env.get("OPENORCHESTRION_AI_PROVIDER")),
            ai_model=(env.get("OPENORCHESTRION_AI_MODEL", DEFAULT_AI_MODEL).strip() or DEFAULT_AI_MODEL),
            ai_timeout_seconds=_positive_float(
                env.get("OPENORCHESTRION_AI_TIMEOUT_SECONDS"),
                default=DEFAULT_AI_TIMEOUT_SECONDS,
                name="OPENORCHESTRION_AI_TIMEOUT_SECONDS",
            ),
        )
