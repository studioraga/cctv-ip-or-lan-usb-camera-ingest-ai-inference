"""Timestamped JPEG/UDP frame protocol for Node2 -> Node1 E2E latency tests.

The default production stream remains RTP/JPEG. This module provides an opt-in
transport used when true sender timestamp + frame_id correlation is required.
Each JPEG frame is split into UDP fragments with a compact binary header:

  magic, version, flags, frame_id, sender_wall_ns, sender_monotonic_ns,
  total_size, fragment_index, fragment_count, payload_size

Node1 computes sender-to-decode latency with receiver_wall_ns - sender_wall_ns.
That requires Node1 and Node2 wall clocks to be synchronized reasonably well
(e.g. chrony on the local LAN). The monotonic timestamp is carried for local
Node2 sequencing/debug only because monotonic clocks are not comparable across
machines.
"""
from __future__ import annotations

import math
import struct
import time
from dataclasses import dataclass
from typing import Dict, Iterable, Iterator, Optional

MAGIC = b"AICAMT1\0"
VERSION = 1
HEADER_STRUCT = struct.Struct("!8sBBQQQIHHH")
HEADER_SIZE = HEADER_STRUCT.size
DEFAULT_MTU_PAYLOAD = 1200
MAX_FRAME_SIZE = 16 * 1024 * 1024
MAX_FRAGMENTS = 65535


@dataclass(frozen=True)
class TimedFramePacket:
    frame_id: int
    sender_wall_ns: int
    sender_monotonic_ns: int
    total_size: int
    fragment_index: int
    fragment_count: int
    payload: bytes
    flags: int = 0

    def pack(self) -> bytes:
        if self.fragment_count <= 0 or self.fragment_count > MAX_FRAGMENTS:
            raise ValueError(f"invalid fragment_count: {self.fragment_count}")
        if self.fragment_index < 0 or self.fragment_index >= self.fragment_count:
            raise ValueError(f"invalid fragment_index: {self.fragment_index}")
        if self.total_size <= 0 or self.total_size > MAX_FRAME_SIZE:
            raise ValueError(f"invalid total_size: {self.total_size}")
        if len(self.payload) > 65535:
            raise ValueError("payload too large for one UDP protocol fragment")
        header = HEADER_STRUCT.pack(
            MAGIC,
            VERSION,
            self.flags,
            int(self.frame_id),
            int(self.sender_wall_ns),
            int(self.sender_monotonic_ns),
            int(self.total_size),
            int(self.fragment_index),
            int(self.fragment_count),
            len(self.payload),
        )
        return header + self.payload


def unpack_packet(data: bytes) -> TimedFramePacket:
    if len(data) < HEADER_SIZE:
        raise ValueError("packet too small")
    magic, version, flags, frame_id, sender_wall_ns, sender_monotonic_ns, total_size, frag_idx, frag_count, payload_size = HEADER_STRUCT.unpack_from(data)
    if magic != MAGIC:
        raise ValueError("bad timed-frame magic")
    if version != VERSION:
        raise ValueError(f"unsupported timed-frame version: {version}")
    payload = data[HEADER_SIZE:]
    if len(payload) != payload_size:
        raise ValueError("payload size mismatch")
    return TimedFramePacket(
        frame_id=frame_id,
        sender_wall_ns=sender_wall_ns,
        sender_monotonic_ns=sender_monotonic_ns,
        total_size=total_size,
        fragment_index=frag_idx,
        fragment_count=frag_count,
        payload=payload,
        flags=flags,
    )


def fragment_jpeg_frame(
    jpeg: bytes,
    frame_id: int,
    sender_wall_ns: Optional[int] = None,
    sender_monotonic_ns: Optional[int] = None,
    max_payload: int = DEFAULT_MTU_PAYLOAD,
) -> Iterator[bytes]:
    if not jpeg:
        raise ValueError("empty JPEG frame")
    if len(jpeg) > MAX_FRAME_SIZE:
        raise ValueError(f"JPEG frame too large: {len(jpeg)} bytes")
    if max_payload <= 0 or max_payload > 65535:
        raise ValueError("max_payload must be in 1..65535")
    sender_wall_ns = time.time_ns() if sender_wall_ns is None else int(sender_wall_ns)
    sender_monotonic_ns = time.monotonic_ns() if sender_monotonic_ns is None else int(sender_monotonic_ns)
    count = int(math.ceil(len(jpeg) / float(max_payload)))
    if count > MAX_FRAGMENTS:
        raise ValueError(f"too many UDP fragments: {count}")
    for idx in range(count):
        start = idx * max_payload
        payload = jpeg[start:start + max_payload]
        yield TimedFramePacket(
            frame_id=int(frame_id),
            sender_wall_ns=sender_wall_ns,
            sender_monotonic_ns=sender_monotonic_ns,
            total_size=len(jpeg),
            fragment_index=idx,
            fragment_count=count,
            payload=payload,
        ).pack()


@dataclass(frozen=True)
class ReassembledTimedFrame:
    frame_id: int
    sender_wall_ns: int
    sender_monotonic_ns: int
    jpeg: bytes
    fragment_count: int


class TimedFrameReassembler:
    """Reassemble timestamped JPEG/UDP fragments into complete JPEG frames."""

    def __init__(self, max_inflight_frames: int = 64):
        if max_inflight_frames <= 0:
            raise ValueError("max_inflight_frames must be positive")
        self.max_inflight_frames = max_inflight_frames
        self._frames: Dict[int, dict] = {}

    def push(self, packet_bytes: bytes) -> Optional[ReassembledTimedFrame]:
        pkt = unpack_packet(packet_bytes)
        entry = self._frames.get(pkt.frame_id)
        if entry is None:
            if len(self._frames) >= self.max_inflight_frames:
                oldest = min(self._frames)
                self._frames.pop(oldest, None)
            entry = {
                "sender_wall_ns": pkt.sender_wall_ns,
                "sender_monotonic_ns": pkt.sender_monotonic_ns,
                "total_size": pkt.total_size,
                "fragment_count": pkt.fragment_count,
                "fragments": {},
            }
            self._frames[pkt.frame_id] = entry
        else:
            if entry["total_size"] != pkt.total_size or entry["fragment_count"] != pkt.fragment_count:
                # Corrupt/reused frame ID. Drop previous state and start again.
                entry = {
                    "sender_wall_ns": pkt.sender_wall_ns,
                    "sender_monotonic_ns": pkt.sender_monotonic_ns,
                    "total_size": pkt.total_size,
                    "fragment_count": pkt.fragment_count,
                    "fragments": {},
                }
                self._frames[pkt.frame_id] = entry

        entry["fragments"][pkt.fragment_index] = pkt.payload
        if len(entry["fragments"]) != entry["fragment_count"]:
            return None

        jpeg = b"".join(entry["fragments"][i] for i in range(entry["fragment_count"]))
        self._frames.pop(pkt.frame_id, None)
        if len(jpeg) != entry["total_size"]:
            raise ValueError("reassembled JPEG size mismatch")
        return ReassembledTimedFrame(
            frame_id=pkt.frame_id,
            sender_wall_ns=entry["sender_wall_ns"],
            sender_monotonic_ns=entry["sender_monotonic_ns"],
            jpeg=jpeg,
            fragment_count=entry["fragment_count"],
        )
