"""Repository policy checks that need to look at files on disk.

``rights`` deliberately stays pure — the evidence model and its audit touch no
filesystem, so they can be reasoned about and tested in isolation. This module
is the thin layer that finds files and applies that audit, and it lives in the
package rather than in a CI script so the test suite can exercise the exact code
CI runs.

The question this answers is "what has this repository committed to shipping",
so the authoritative list of files is what Git tracks, not what happens to be on
disk. A developer who generates the conformance suite into ``build/`` has MIDI
in their working tree that the repository does not carry, and a check that
walked the filesystem would fail for them and nobody else.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
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


class NotATrackedTreeError(RuntimeError):
    """Raised when the tracked-file list cannot be obtained.

    Deliberately fatal rather than an empty result. A rights check that quietly
    finds nothing to audit reports success, which is the one outcome it must
    never produce by accident.
    """


def tracked_midi_files(repo_root: str | Path) -> list[Path]:
    """Every MIDI file this repository tracks, anywhere in the tree.

    Scoped to Git rather than the filesystem for two reasons. The policy is about
    what the repository distributes, and that is exactly what Git tracks — an
    untracked download in someone's working copy is their business. And the
    project generates its conformance suite into an ignored directory, so a
    filesystem walk would fail on a developer's machine for files the repository
    never carried.
    """
    root = Path(repo_root)
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise NotATrackedTreeError(
            f"cannot list tracked files in {root} ({exc}); "
            "this check must run inside a Git checkout"
        ) from None

    names = completed.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    return sorted(
        root / name
        for name in names
        if name and Path(name).suffix.lower() in MIDI_SUFFIXES
    )


def audit_music_files(paths: Iterable[str | Path]) -> list[str]:
    """Every given MIDI file that is not established as redistributable.

    The project's position is that a downloadable file is not a redistributable
    one. That policy is worth only as much as the check behind it: without one,
    a single convenient ``git add`` of somebody's collection is all it takes, and
    once the diff is large the mistake is invisible in review.

    A file must be covered either by a ``.json`` sidecar or by a curation
    manifest row, and that evidence must support a ``verified-open`` claim.
    Returns one message per offending file, empty when the tree is clean, so the
    caller decides how loudly to fail.
    """
    offenders: list[str] = []
    for candidate in paths:
        path = Path(candidate)
        if path.suffix.lower() not in MIDI_SUFFIXES:
            continue
        if not path.is_file():
            # Tracked but absent from the working tree: nothing to audit, and
            # not this check's business to explain why.
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


def audit_committed_music(directory: str | Path) -> list[str]:
    """Audit every MIDI file under one directory, tracked or not.

    Retained for auditing a candidate set before it is committed, and for tests
    that build a tree without a Git repository around it. The repository-wide
    contract uses :func:`audit_tracked_music`.
    """
    root = Path(directory)
    if not root.is_dir():
        return []
    return audit_music_files(sorted(root.rglob("*")))


def audit_tracked_music(repo_root: str | Path) -> list[str]:
    """The repository-wide contract: no tracked MIDI without established rights.

    Scoped to the whole repository rather than one directory because the rule is
    about what this project distributes, and Git does not care which folder a
    file sits in. A rejected candidate parked in a research directory is still
    published the moment it is pushed.
    """
    return audit_music_files(tracked_midi_files(repo_root))


def count_tracked_music(repo_root: str | Path) -> int:
    """How many MIDI files the repository tracks, so a check reports its scope."""
    return len(tracked_midi_files(repo_root))


def count_committed_music(directory: str | Path) -> int:
    """How many MIDI files a directory carries, for a check that reports its scope."""
    root = Path(directory)
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*") if path.suffix.lower() in MIDI_SUFFIXES)


__all__ = [
    "MIDI_SUFFIXES",
    "NotATrackedTreeError",
    "audit_committed_music",
    "audit_music_files",
    "audit_tracked_music",
    "count_committed_music",
    "count_tracked_music",
    "tracked_midi_files",
]
