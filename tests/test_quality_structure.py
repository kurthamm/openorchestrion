"""Check musical counterexamples through raw MIDI, not threshold-only mocks."""

import hashlib
import io
import json

from mido import Message, MidiFile, MidiTrack

from openorchestrion.library.quality import analyze
from openorchestrion.library.quality_plan import build
from openorchestrion.library.quality_structure import infer, structure


def arrangement(*, melody_only=False, implicit=False, muted=False):
    events = [] if implicit else [Message("program_change", program=0)]
    if muted:
        events.append(Message("control_change", control=11, value=0))
    for i in range(144):
        pitches = [60 + i % 12] if melody_only else [36 + i % 12, 48 + i % 12, 60 + i % 12, 72 + i % 12]
        duration = 100 + i % 12 * 11
        for j, pitch in enumerate(pitches):
            events.append(Message("note_on", note=pitch, velocity=60 + i % 24, time=960 - duration if j == 0 else 0))
        for j, pitch in enumerate(pitches):
            events.append(Message("note_off", note=pitch, time=duration if j == 0 else 0))
    midi = MidiFile()
    midi.tracks = [MidiTrack(events)]
    stream = io.BytesIO()
    midi.save(file=stream)
    raw = stream.getvalue()
    return {"asset_id": "sha256:" + hashlib.sha256(raw).hexdigest(), "facts": analyze(raw)}, structure(raw)


def test_substantial_two_register_arrangement_is_explicitly_an_inference():
    entry, measured = arrangement()
    result = infer(entry, measured)
    assert result["arrangement"] == "solo_piano"
    assert result["inference"] is True
    assert result["performance_capture"] is False


def test_long_expressive_melody_alone_does_not_prove_complete_arrangement():
    entry, measured = arrangement(melody_only=True)
    assert infer(entry, measured) is None


def test_default_piano_and_muted_events_do_not_supply_arrangement_evidence():
    for kwargs in ({"implicit": True}, {"muted": True}):
        entry, measured = arrangement(**kwargs)
        assert infer(entry, measured) is None


def test_structural_inference_cannot_override_verified_individual_part(tmp_path):
    entry, measured = arrangement()
    root = tmp_path / "library"
    (root / "assets").mkdir(parents=True)
    name = entry["asset_id"][7:] + ".json"
    (root / "assets" / name).write_bytes(b"{}")
    entry.update(original_location="assets/" + name, sidecar_sha256=hashlib.sha256(b"{}").hexdigest(), title="Published individual part")
    facts = tmp_path / "facts.jsonl"
    facts.write_text(json.dumps(entry) + "\n")
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({entry["asset_id"]: {"completeness": "partial", "bundle_midi_count": 4, "sounding_channels": 1}}))
    metrics = tmp_path / "structure.jsonl"
    metrics.write_text(json.dumps({"asset_id": entry["asset_id"], "structure": measured, "inference": infer(entry, measured)}) + "\n")
    plan = build(root, facts, [evidence], metrics)
    assert plan["entries"][0]["status"] == "excluded"
    assert "confirmed_partial_arrangement" in plan["entries"][0]["reasons"]
