"""``openorchestrion-stage-candidate`` — turn a downloaded file into a reviewable candidate.

Curation research and file retrieval do not always happen in the same place. The
person who can read a license page may be unable to commit, and the machine that
can commit may be unable to reach the archive at all. This is the seam between
those two halves: given a file that something else fetched, it verifies the file
is what the research was about and writes the manifest row that vouches for it.

Nothing here touches the network. That is deliberate — every check in this module
is a pure function of a file and a claim, so the whole thing is testable without
a fixture server, and the one step that genuinely needs the internet stays in the
CI job where it can be reviewed as three lines of YAML.

The order of checks is the point:

1. **Host** — is this even a source the project has agreed to work through?
2. **Digest** — are these the bytes the research was about?
3. **MIDI** — is it music at all, or an error page with a ``.mid`` name?
4. **Rights** — does the evidence support the claim being made?

A file that fails any of them never reaches a manifest.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from openorchestrion.midi.analyzer import analyze_midi

from .importer import DEFAULT_MAX_BYTES, SUPPORTED_EXTENSIONS
from .rights import (
    COMPOSITION_RIGHTS,
    ESTABLISHED_LICENSES,
    REDISTRIBUTION,
    RIGHTS_STATUSES,
    RightsError,
    RightsEvidence,
    verify,
)

#: Archives this project has agreed to work through, from music/starter-catalog.md.
#:
#: An allowlist rather than a warning, because the alternative is a job that pulls
#: any URL on the internet into the repository and opens a pull request for it.
#: Adding a host is a deliberate edit that records the decision, exactly like
#: adding a license to the established table.
ALLOWED_SOURCE_HOSTS: frozenset[str] = frozenset(
    {
        "commons.wikimedia.org",
        "upload.wikimedia.org",
        "www.mutopiaproject.org",
        "mutopiaproject.org",
        "imslp.org",
        "s.imslp.org",
    }
)

MANIFEST_COLUMNS: tuple[str, ...] = (
    "path",
    "sha256",
    "rights_status",
    "source_reference",
    "source_label",
    "license",
    "license_url",
    "attribution",
    "composition_rights",
    "composition_rights_basis",
    "redistribution",
    "verified_by",
    "verified_at",
)


class CandidateError(ValueError):
    """Raised when a candidate cannot be staged, with the reason a curator needs."""


@dataclass(frozen=True, slots=True)
class StagedCandidate:
    """One candidate that passed every check, and what was learned about it."""

    filename: str
    sha256: str
    size_bytes: int
    note_count: int
    duration_seconds: float
    peak_simultaneous_notes: int
    digest_was_verified: bool
    """Whether the digest was checked against a researched value, or merely observed.

    A recorded digest proves the committed bytes are the bytes someone read a
    license for. An observed one proves only that these bytes are internally
    consistent, which is a much weaker claim, so a reviewer has to be told which
    of the two they are looking at.
    """


def check_source_host(url: str) -> None:
    """Refuse a URL from anywhere this project has not agreed to work through."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
    except ValueError as exc:
        raise CandidateError(f"unreadable source URL: {exc}") from None
    if not host:
        raise CandidateError(f"source URL has no host: {url!r}")
    if parsed.scheme.casefold() != "https":
        raise CandidateError("source URL must use HTTPS")
    if host not in ALLOWED_SOURCE_HOSTS:
        raise CandidateError(
            f"{host} is not an allowed source. This project works through "
            f"{', '.join(sorted(ALLOWED_SOURCE_HOSTS))}. Add a host to "
            "ALLOWED_SOURCE_HOSTS after deciding it belongs there."
        )


def _safe_target_name(value: str) -> str:
    """Return a plain MIDI basename or refuse a path/alternate extension.

    ``filename`` crosses from a workflow input into a repository write. It must
    never be able to escape the candidate directory, and a MIDI hidden under an
    unrelated extension would evade the repository-wide ``.mid``/``.midi`` audit.
    """
    candidate = value.strip()
    path = Path(candidate)
    if (
        not candidate
        or path.is_absolute()
        or path.name != candidate
        or "/" in candidate
        or "\\" in candidate
    ):
        raise CandidateError("filename must be a plain basename inside the candidate directory")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise CandidateError("filename must end in .mid or .midi")
    return candidate


def _digest(path: Path) -> str:
    handle = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            handle.update(block)
    return handle.hexdigest()


def stage_candidate(
    file_path: str | Path,
    destination: str | Path,
    rights: RightsEvidence,
    *,
    filename: str | None = None,
    expected_sha256: str | None = None,
    source_url: str | None = None,
    max_bytes: int | None = DEFAULT_MAX_BYTES,
) -> StagedCandidate:
    """Verify a downloaded file and record it in the destination's manifest.

    ``expected_sha256`` is optional but not decorative. Supplied, it proves the
    file is the one whose license was actually read. Omitted, the digest is
    computed and recorded, and the result says so — because "I checked this
    file's terms" and "I checked some file's terms and this is a file" are
    different claims and must not look alike in review.
    """
    source = Path(file_path)
    if not source.is_file():
        raise CandidateError(f"{source} does not exist")

    if source_url is not None:
        check_source_host(source_url)

    target_name = _safe_target_name(filename or source.name)

    size = source.stat().st_size
    if size == 0:
        raise CandidateError(f"{source} is empty; the download produced nothing")
    if max_bytes is not None and size > max_bytes:
        raise CandidateError(f"{source} is {size} bytes, above the {max_bytes} byte limit")

    actual = _digest(source)
    verified = expected_sha256 is not None
    if verified and actual != (expected_sha256 or "").lower():
        raise CandidateError(
            f"digest mismatch: researched {expected_sha256}, downloaded {actual}. "
            "The evidence was gathered about a different file, or the download is corrupt."
        )

    try:
        analysis = analyze_midi(source)
    except Exception as exc:  # noqa: BLE001 - any parse failure means it is not usable music
        raise CandidateError(
            f"{source} is not a readable MIDI file ({type(exc).__name__}: {exc}). "
            "Archives serve error pages and HTML with .mid names."
        ) from None
    if not analysis.note_count:
        raise CandidateError(f"{source} parses but contains no notes")

    try:
        verify(rights)
    except RightsError as exc:
        raise CandidateError(str(exc)) from None

    destination_dir = Path(destination)
    destination_dir.mkdir(parents=True, exist_ok=True)
    (destination_dir / target_name).write_bytes(source.read_bytes())

    _append_manifest_row(
        destination_dir / "catalog.csv",
        {"path": target_name, "sha256": actual, **rights.to_dict()},
    )

    return StagedCandidate(
        filename=target_name,
        sha256=actual,
        size_bytes=size,
        note_count=analysis.note_count,
        duration_seconds=analysis.duration_seconds,
        peak_simultaneous_notes=analysis.peak_simultaneous_notes,
        digest_was_verified=verified,
    )


def _append_manifest_row(manifest: Path, values: dict[str, object]) -> None:
    """Add one row, replacing any existing row for the same file.

    Re-staging a candidate after correcting its evidence must not leave two rows
    disagreeing about the same file; the audit would then depend on which one a
    reader happened to see first.
    """
    rows: list[dict[str, str]] = []
    if manifest.is_file():
        with manifest.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = [row for row in csv.DictReader(handle) if row.get("path") != values["path"]]

    rows.append({name: str(values.get(name) or "") for name in MANIFEST_COLUMNS})
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item.get("path") or ""):
            writer.writerow({name: row.get(name, "") for name in MANIFEST_COLUMNS})


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="openorchestrion-stage-candidate",
        description=(
            "Verify a downloaded MIDI candidate and record it in a curation manifest. "
            "Refuses anything whose digest, format or evidence does not hold up."
        ),
    )
    parser.add_argument("--file", required=True, help="The downloaded file to stage")
    parser.add_argument("--into", required=True, help="Candidate directory to write into")
    parser.add_argument("--filename", help="Plain .mid/.midi basename to store")
    parser.add_argument("--source-url", help="HTTPS URL it was downloaded from; checked against policy")
    parser.add_argument(
        "--expected-sha256",
        help="Digest of the file whose license was read. Omit only if it was not recorded.",
    )
    parser.add_argument("--rights-status", choices=RIGHTS_STATUSES, default="verified-open")
    parser.add_argument("--source-reference", help="URL of the item record")
    parser.add_argument("--source-label")
    parser.add_argument(
        "--license",
        dest="license_name",
        help=f"File license. Established ids: {', '.join(ESTABLISHED_LICENSES)}",
    )
    parser.add_argument("--license-url")
    parser.add_argument("--attribution")
    parser.add_argument("--composition-rights", choices=COMPOSITION_RIGHTS, default="unknown")
    parser.add_argument("--composition-rights-basis")
    parser.add_argument("--redistribution", choices=REDISTRIBUTION, default="unknown")
    parser.add_argument("--verified-by")
    parser.add_argument("--verified-at")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    rights = RightsEvidence(
        rights_status=args.rights_status,
        source_reference=args.source_reference,
        source_label=args.source_label,
        license=args.license_name,
        license_url=args.license_url,
        attribution=args.attribution,
        composition_rights=args.composition_rights,
        composition_rights_basis=args.composition_rights_basis,
        redistribution=args.redistribution,
        verified_at=args.verified_at,
        verified_by=args.verified_by,
    )

    try:
        staged = stage_candidate(
            args.file,
            args.into,
            rights,
            filename=args.filename,
            expected_sha256=args.expected_sha256,
            source_url=args.source_url,
        )
    except CandidateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    print(f"staged {staged.filename}")
    print(f"  sha256:   {staged.sha256}")
    print(f"  size:     {staged.size_bytes} bytes")
    print(f"  music:    {staged.note_count} notes, {staged.duration_seconds:.1f}s, "
          f"peak {staged.peak_simultaneous_notes} voices")
    if staged.digest_was_verified:
        print("  digest:   matches the researched value")
    else:
        print("  digest:   OBSERVED, not verified — no researched digest was supplied")


if __name__ == "__main__":
    main()
