"""Repository policy checks that need to look at files on disk.

``rights`` deliberately stays pure — the evidence model and its audit touch no
filesystem, so they can be reasoned about and tested in isolation. This module
is the thin layer that walks a directory and applies that audit, and it lives in
the package rather than in a CI script so the test suite can exercise the exact
code CI runs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .importer import ManifestError, read_curation_manifest
from .rights import RightsEvidence, audit

MIDI_SUFFIXES = {".mid", ".midi"}


def _manifest_coverage(directory: Path) -> dict[str, tuple[RightsEvidence, str | None]]:
    """Evidence for each file a manifest in this directory vouches for.

    Committed repertoire keeps its evidence in the curation manifest rather than
    in a sidecar per file. That is not a storage preference: the manifest is what
    the installer reads, so making it the same artifact the contract check reads
    means the claim CI verifies is the claim the appliance acts on. A per-file
    sidecar committed alongside would be a second copy of the same assertion,
    free to drift from the one that actually takes effect.
    """
    coverage: dict[str, tuple[RightsEvidence, str | None]] = {}
    for manifest in sorted(directory.glob("*.csv")):
        try:
            entries = read_curation_manifest(manifest)
        except ManifestError:
            # Reported against the files it fails to cover, so a broken manifest
            # surfaces as unestablished rights rather than as a parse error
            # nobody connects to the music it was supposed to vouch for.
            continue
        for entry in entries:
            coverage[Path(entry.path).name] = (entry.rights, entry.expected_sha256)
    return coverage


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        coverage = _manifest_coverage(path.parent)

        sidecar = path.with_suffix(".json")
        covered, expected_digest = coverage.get(path.name, (None, None))

        if sidecar.is_file():
            try:
                document = json.loads(sidecar.read_text(encoding="utf-8"))
                provenance = document.get("provenance") or {}
                evidence = RightsEvidence.from_mapping(provenance)
            except (OSError, ValueError) as exc:
                # RightsError is a ValueError, so a malformed provenance block
                # and an unreadable file land here together: both mean the claim
                # cannot be checked, which is the same answer as not having one.
                offenders.append(f"{path}: unreadable provenance ({exc})")
                continue
        elif covered is not None:
            evidence = covered
            if expected_digest is not None and _digest(path) != expected_digest:
                # The committed bytes are not the bytes anyone verified. Swapping
                # a file without updating its row is how a starter catalog ends
                # up shipping something nobody checked.
                offenders.append(
                    f"{path}: does not match the digest its manifest row records"
                )
                continue
        else:
            offenders.append(
                f"{path}: no sidecar or manifest row recording its rights"
            )
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
