from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import mido

ALSA_SEQUENCER_CLIENTS = Path("/proc/asound/seq/clients")

_ALSA_ADDRESS = re.compile(r"^(?P<base>.*\S)\s+(?P<client>\d+):(?P<port>\d+)$")
_SEQ_CLIENT = re.compile(r'^Client\s+(?P<number>\d+)\s*:\s*"(?P<name>.*)"')
_SEQ_PORT = re.compile(r'^\s+Port\s+(?P<number>\d+)\s*:\s*"(?P<name>.*)"')
_SEQ_LINK = re.compile(r"^\s+Connecting To:\s*(?P<targets>.*)$")
_SEQ_TARGET = re.compile(r"(\d+):(\d+)")


def list_output_ports() -> list[str]:
    """Return currently available MIDI output names."""
    return list(mido.get_output_names())


def find_output_port(match: str) -> str | None:
    """Find the first output port containing a case-insensitive match."""
    needle = match.casefold()
    for name in list_output_ports():
        if needle in name.casefold():
            return name
    return None


def port_base_name(name: str) -> str:
    """Strip the ALSA ``client:port`` suffix that changes when a device re-enumerates."""
    match = _ALSA_ADDRESS.match(name)
    return match.group("base") if match else name


def port_link_target(name: str) -> tuple[int, int] | None:
    """The ALSA ``(client, port)`` address embedded in an rtmidi port name."""
    match = _ALSA_ADDRESS.match(name)
    if match is None:
        return None
    return int(match.group("client")), int(match.group("port"))


def is_kernel_loopback_port(name: str) -> bool:
    """True for the ALSA ``snd-seq-dummy`` Midi Through ports, which are never instruments."""
    return port_base_name(name).startswith("Midi Through")


def resolve_output_port(name: str, available: list[str]) -> str | None:
    """Find the current port for a device, even if ALSA renumbered it after a replug."""
    if name in available:
        return name
    base = port_base_name(name)
    for candidate in available:
        if port_base_name(candidate) == base:
            return candidate
    return None


@dataclass(slots=True)
class SequencerPort:
    number: int
    name: str
    connecting_to: set[tuple[int, int]] = field(default_factory=set)


@dataclass(slots=True)
class SequencerClient:
    number: int
    name: str
    ports: dict[int, SequencerPort] = field(default_factory=dict)


def parse_sequencer_clients(text: str) -> dict[int, SequencerClient]:
    """Parse ``/proc/asound/seq/clients`` into clients, ports and their subscriptions."""
    clients: dict[int, SequencerClient] = {}
    client: SequencerClient | None = None
    port: SequencerPort | None = None
    for line in text.splitlines():
        match = _SEQ_CLIENT.match(line)
        if match:
            client = SequencerClient(int(match.group("number")), match.group("name"))
            clients[client.number] = client
            port = None
            continue
        if client is None:
            continue
        match = _SEQ_PORT.match(line)
        if match:
            port = SequencerPort(int(match.group("number")), match.group("name"))
            client.ports[port.number] = port
            continue
        match = _SEQ_LINK.match(line)
        if match and port is not None:
            port.connecting_to.update(
                (int(target), int(target_port))
                for target, target_port in _SEQ_TARGET.findall(match.group("targets"))
            )
    return clients


def client_link_targets(
    clients: dict[int, SequencerClient],
    client_name: str,
) -> set[tuple[int, int]]:
    """Every ``(client, port)`` address a named sequencer client is subscribed to."""
    targets: set[tuple[int, int]] = set()
    for client in clients.values():
        if client.name != client_name:
            continue
        for port in client.ports.values():
            targets.update(port.connecting_to)
    return targets


def read_sequencer_clients(path: Path = ALSA_SEQUENCER_CLIENTS) -> dict[int, SequencerClient] | None:
    """Current sequencer table, or None where the kernel does not expose one."""
    if not path.is_file():
        return None
    return parse_sequencer_clients(path.read_text())
