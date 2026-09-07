"""Read SMF events without allocating a Mido message object for every event.

Used only by offline curation. Playback continues to use the established loader.
Events preserve track/sequence tie order and include meta events for timing.
"""
from __future__ import annotations

import struct


def read_events(raw: bytes) -> tuple[int, int, list[tuple]]:
    if raw[:4] != b"MThd" or len(raw) < 14:
        raise ValueError("invalid MIDI header")
    header_length = struct.unpack_from(">I", raw, 4)[0]
    kind, tracks, division = struct.unpack_from(">HHh", raw, 8)
    if header_length < 6 or kind > 2 or division <= 0 or not tracks:
        raise ValueError("unsupported MIDI header or time division")
    offset = 8 + header_length
    events = []
    for track in range(tracks):
        if raw[offset:offset + 4] != b"MTrk" or offset + 8 > len(raw):
            raise ValueError("missing MIDI track")
        size = struct.unpack_from(">I", raw, offset + 4)[0]
        offset += 8
        end = offset + size
        if end > len(raw):
            raise ValueError("truncated MIDI track")
        tick = sequence = 0
        running = None
        while offset < end:
            delta = 0
            while True:
                if offset >= end:
                    raise ValueError("truncated delta time")
                b = raw[offset]
                offset += 1
                delta = (delta << 7) | (b & 127)
                if b < 128:
                    break
            tick += delta
            if offset >= end:
                raise ValueError("missing event")
            status = raw[offset]
            if status < 128:
                if running is None:
                    raise ValueError("running status without channel status")
                status = running
            else:
                offset += 1
                if status < 240:
                    running = status
            if status in (240, 247, 255):
                meta = None
                if status == 255:
                    if offset >= end:
                        raise ValueError("missing meta type")
                    meta = raw[offset]
                    offset += 1
                length = 0
                while True:
                    if offset >= end:
                        raise ValueError("truncated event length")
                    b = raw[offset]
                    offset += 1
                    length = (length << 7) | (b & 127)
                    if b < 128:
                        break
                if offset + length > end:
                    raise ValueError("truncated variable event")
                payload = raw[offset:offset + length]
                offset += length
                if meta is not None:
                    payload = bytes((meta,)) + payload
                else:
                    status = 240
                    payload = payload.removeprefix(b'\xf0').removesuffix(b'\xf7')
                    if any(x > 127 for x in payload):
                        raise ValueError("non-data byte in SysEx")
            elif 128 <= status < 240:
                length = 1 if status >> 4 in (12, 13) else 2
                if offset + length > end:
                    raise ValueError("truncated channel event")
                payload = raw[offset:offset + length]
                offset += length
                if any(x > 127 for x in payload):
                    raise ValueError("non-data byte in channel event")
            else:
                raise ValueError("unsupported system event in MIDI file")
            events.append((tick, track, sequence, status, payload))
            sequence += 1
    events.sort(key=lambda e: e[:3])
    return kind, division, events
