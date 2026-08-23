"""Repository policy checks that need to look at files on disk.

``rights`` deliberately stays pure — the evidence model and its audit touch no
filesystem, so they can be reasoned about and tested in isolation. This module
is the thin layer that walks a directory and applies that audit, and it lives in
the package rather than in a CI script so the test suite can exercise the exact
code CI runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from .rights import RightsEvidence, audit

MIDI_SUFFIXES = {".mid", ".midi"}


def audit_committed_music(directory: str | Path) -> list[str]:
    """Every committed MIDI file that is not established as redistributable.

    The project's position is that a downloadable file is not a redistributable
    one, and that the starter catalog is assembled on the appliance rather than
    committed to Git. That policy is worth only as much as the check behind it:
    without one, a single convenient ``git add`` of somebody's collection is all
    it takes, and once the diff is large the mistake is invisible in review.

    A committed MIDI file must sit beside a ``.json`` sidecar whose provenance
    supports a ``verified-open`` claim. Returns one message per offending file,
    empty when the tree is clean, so the caller decides how loudly to fail.
    """
    root = Path(directory)
    if not root.is_dir():
        return []

    offenders: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in MIDI_SUFFIXES:
            continue

        sidecar = path.with_suffix(".json")
        if not sidecar.is_file():
            offenders.append(f"{path}: no sidecar recording its rights")
            continue

        try:
            document = json.loads(sidecar.read_text(encoding="utf-8"))
            provenance = document.get("provenance") or {}
            evidence = RightsEvidence.from_mapping(provenance)
        except (OSError, ValueError) as exc:
            # RightsError is a ValueError, so a malformed provenance block and an
            # unreadable file land here together: both mean the claim cannot be
            # checked, which is the same answer as not having one.
            offenders.append(f"{path}: unreadable provenance ({exc})")
            continue

        if evidence.rights_status != "verified-open":
            offenders.append(
                f"{path}: rights_status is {evidence.rights_status!r}, "
                "which is not redistributable"
            )
            continue

        reasons = audit(evidence)
        if reasons:
            offenders.append(f"{path}: {reasons[0]}")

    return offenders


def count_committed_music(directory: str | Path) -> int:
    """How many MIDI files the tree carries, for a check that reports its scope."""
    root = Path(directory)
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*") if path.suffix.lower() in MIDI_SUFFIXES)


__all__ = ["MIDI_SUFFIXES", "audit_committed_music", "count_committed_music"]
