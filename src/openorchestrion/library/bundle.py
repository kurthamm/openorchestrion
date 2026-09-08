"""Bounded, offline inspection of MIDI ZIP bundles; never publishes music."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from openorchestrion.midi.analyzer import analyze_midi

MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_MEMBERS = 256


def inspect_bundle(path: Path, *, expected_sha256: str) -> dict:
    """Audit every member in memory. No ZIP paths are written to disk.

    A member's digest identifies it separately from the bundle. Readable MIDI
    does not imply musical quality, arrangement completeness or redistribution
    permission. Those remain independent admission requirements.
    """
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds the 32 MiB limit")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256.lower():
        raise ValueError("archive digest does not match the researched bundle")
    records = []
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = archive.infolist()
        if len(members) > MAX_MEMBERS:
            raise ValueError("archive exceeds the 256 member limit")
        seen = set()
        total = 0
        for member in members:
            name = member.filename
            parts = PurePosixPath(name).parts
            mode = member.external_attr >> 16
            if (not parts or name.startswith("/") or "\\" in name or ":" in name
                    or ".." in parts or name.casefold() in seen):
                raise ValueError(f"unsafe or duplicate archive member: {name!r}")
            seen.add(name.casefold())
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in
                                    (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError(f"non-regular archive member: {name!r}")
            if member.flag_bits & 1:
                raise ValueError("encrypted bundles are unsupported")
            total += member.file_size
            if member.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                raise ValueError("archive exceeds uncompressed size limits")
            if member.is_dir():
                records.append({"member": name, "status": "directory"})
                continue
            with archive.open(member) as stream:
                content = stream.read(MAX_MEMBER_BYTES + 1)
            if len(content) != member.file_size or len(content) > MAX_MEMBER_BYTES:
                raise ValueError("archive member size mismatch")
            record = {"member": name, "sha256": hashlib.sha256(content).hexdigest(),
                      "size_bytes": len(content), "status": "not-midi"}
            if PurePosixPath(name).suffix.lower() in {".mid", ".midi"}:
                try:
                    with tempfile.TemporaryDirectory(prefix="openorchestrion-bundle-") as tmp:
                        midi = Path(tmp) / "candidate.mid"
                        midi.write_bytes(content)
                        analysis = analyze_midi(midi)
                    record.update(status="readable-midi" if analysis.note_count else "empty-midi",
                                  analysis=analysis.to_dict())
                except Exception as exc:  # malformed music must not hide other members
                    record.update(status="invalid-midi", error=f"{type(exc).__name__}: {exc}")
            records.append(record)
    return {"archive_sha256": digest, "archive_bytes": len(raw), "members": records,
            "admitted": False, "notice": "Inspection only; per-file rights and quality required."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = inspect_bundle(args.file, expected_sha256=args.expected_sha256)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Audited {len(report['members'])} members; no files admitted.")


if __name__ == "__main__":
    main()
