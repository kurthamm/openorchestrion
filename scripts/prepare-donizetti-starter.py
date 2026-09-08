"""Reproduce two licensed starter derivatives from the exact publisher ZIP.

Only the mislabeled viola program/name changes. No notes, timing, dynamics,
controllers, tracks, or musical structure are added, removed, or humanized.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile

import mido

from openorchestrion.library.acquire import stage_candidate
from openorchestrion.library.bundle import inspect_bundle
from openorchestrion.library.rights import RightsEvidence

ARCHIVE_SHA256 = "7cf540ae644fe96d5f1e596ad0e19015f7a628a873a0d46212afd6040be42284"
ITEM = "https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=342"
SELECTION = [
    ("quart18-score.mid", "quart18-viola.mid", "donizetti-quartet18-movement1.mid"),
    ("quart18-score-3.mid", "quart18-viola-3.mid", "donizetti-quartet18-movement4.mid"),
]


def note_events(track):
    tick = 0
    events = []
    for msg in track:
        tick += msg.time
        if msg.type in {"note_on", "note_off"}:
            # Simultaneous chord ordering and instrument-specific velocity differ
            # in LilyPond's separate-part exports; pitches/onsets/releases agree.
            events.append((tick, msg.type, msg.note))
    return sorted(events)


def prepare(archive_path, output):
    audit = inspect_bundle(archive_path, expected_sha256=ARCHIVE_SHA256)
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"archive_sha256": ARCHIVE_SHA256, "source_reference": ITEM,
                "member_audit": [{k: v for k, v in row.items() if k != "analysis"}
                                 for row in audit["members"]], "derivatives": []}
    with zipfile.ZipFile(archive_path) as archive:
        for member, viola_member, name in SELECTION:
            original = archive.read(member)
            midi = mido.MidiFile(file=io.BytesIO(original))
            part = mido.MidiFile(file=io.BytesIO(archive.read(viola_member)))
            assert midi.ticks_per_beat == part.ticks_per_beat
            assert midi.tracks[3].name == "viola:"
            assert note_events(midi.tracks[3]) == note_events(part.tracks[1])
            before = [[msg.dict() for msg in track] for track in midi.tracks]
            corrections = []
            for index, msg in enumerate(midi.tracks[3]):
                if msg.type == "program_change":
                    assert msg.channel == 2 and msg.program == 42 and msg.time == 0
                    midi.tracks[3][index] = msg.copy(program=41)
                    corrections.append({"track": 3, "event": index,
                                        "from": msg.dict(), "to": midi.tracks[3][index].dict()})
                elif msg.type == "instrument_name":
                    assert msg.name == "cello"
                    midi.tracks[3][index] = msg.copy(name="viola")
                    corrections.append({"track": 3, "event": index,
                                        "from": msg.dict(), "to": midi.tracks[3][index].dict()})
            assert len(corrections) == 3
            stream = io.BytesIO()
            midi.save(file=stream)
            derived = stream.getvalue()
            after_midi = mido.MidiFile(file=io.BytesIO(derived))
            after = [[msg.dict() for msg in track] for track in after_midi.tracks]
            expected = [[dict(msg) for msg in track] for track in before]
            for change in corrections:
                expected[change["track"]][change["event"]] = change["to"]
            assert after == expected
            digest = hashlib.sha256(derived).hexdigest()
            # Write to a temporary plain name, then use normal rights-aware staging.
            import tempfile
            with tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / name
                source.write_bytes(derived)
                stage_candidate(source, output, RightsEvidence(
                    rights_status="verified-open", source_reference=ITEM,
                    source_label="Mutopia Project; documented OpenOrchestrion derivative",
                    license="public-domain", license_url="https://www.mutopiaproject.org/legal.html",
                    attribution="Gaetano Donizetti; typeset by Maurizio Tomasi, updated by Felix Janda. "
                                "OpenOrchestrion corrects only the viola MIDI program/name; see repertoire audit.",
                    composition_rights="public-domain",
                    composition_rights_basis="Donizetti died 1848; quartet composed 1836; "
                                             "Mutopia item 342 declares this edition Public Domain.",
                    redistribution="permitted", verified_by="OpenOrchestrion source and derivative audit",
                    verified_at="2026-09-08T00:00:00+00:00"),
                    expected_sha256=digest, filename=name)
            evidence["derivatives"].append({"path": name, "source_member": member,
                "source_sha256": hashlib.sha256(original).hexdigest(), "sha256": digest,
                "corrections": corrections, "other_events_identical": True,
                "viola_note_timing_matches_publisher_part": True})
    (output / "donizetti-derivation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.archive, args.output), indent=2))
