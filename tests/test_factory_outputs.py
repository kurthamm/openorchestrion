"""The production output list must contain only real instruments."""

from __future__ import annotations

from pathlib import Path

from openorchestrion.playback import factory


class _Settings:
    def __init__(self, tmp_path: Path) -> None:
        self.history_db = tmp_path / "history.db"
        self.virtual_midi = False


def test_kernel_midi_through_is_not_an_output(tmp_path: Path, monkeypatch) -> None:
    """ALSA's snd-seq-dummy loopback is always present and never an instrument.

    Counting it as an output made capability-aware routing spread a
    multi-channel orchestral file between the keyboard and a port nobody hears.
    """
    monkeypatch.setattr(
        factory,
        "list_output_ports",
        lambda: [
            "Midi Through:Midi Through Port-0 14:0",
            "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 24:0",
        ],
    )
    engine = factory.create_default_playback(_Settings(tmp_path))
    assert engine.output_names == ("CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 24:0",)
    assert engine.router.default_device == "CASIO USB-MIDI:CASIO USB-MIDI MIDI 1 24:0"


def test_only_loopback_present_means_no_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(factory, "list_output_ports", lambda: ["Midi Through:Midi Through Port-0 14:0"])
    engine = factory.create_default_playback(_Settings(tmp_path))
    assert engine.output_names == ()
    assert engine.outputs_ready is False
