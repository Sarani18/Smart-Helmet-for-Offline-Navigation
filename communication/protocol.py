"""
Smart Helmet Protocol
---------------------
Defines the binary packet format used for all communication between
the mobile application and the helmet microcontroller.

Packet structure (8 bytes total, big-endian):
┌───────────┬──────────┬────────────────┬───────────────┬──────────┐
│  MAGIC    │  TYPE    │  SEQUENCE NUM  │   PAYLOAD     │ CHECKSUM │
│  1 byte   │  1 byte  │    2 bytes     │   3 bytes     │  1 byte  │
│   0xAB    │          │                │               │  XOR sum │
└───────────┴──────────┴────────────────┴───────────────┴──────────┘
"""

from __future__ import annotations

from enum import IntEnum
from typing import NamedTuple


MAGIC_BYTE = 0xAB
PACKET_SIZE = 8


class PacketType(IntEnum):
    """All valid packet type codes in the Smart Helmet protocol."""

    # Navigation instructions (app → helmet)
    NAV_INSTRUCTION = 0x01   # turn instruction + distance
    GPS_STATUS = 0x02        # GPS active / lost flag
    SPEED_UPDATE = 0x03      # current speed

    # Telemetry (helmet → app)
    IMU_DATA = 0x10          # accelerometer + gyroscope reading
    BATTERY_LEVEL = 0x11     # battery percentage
    ACK = 0x12               # general acknowledgement

    # Safety events (bidirectional)
    CRASH_EVENT = 0x20       # crash detected
    SOS_CONFIRM = 0x21       # SOS acknowledged by app

    # Control
    HEARTBEAT = 0xFE
    RESET = 0xFF


class Packet(NamedTuple):
    """
    A fully parsed Smart Helmet protocol packet.

    Attributes
    ----------
    packet_type : PacketType
        What kind of data this packet carries.
    sequence_number : int
        Rolling counter used for ordering and duplicate detection (0–65535).
    payload : bytes
        Up to 3 bytes of type-specific data.
    """

    packet_type: PacketType
    sequence_number: int
    payload: bytes


class SmartHelmetProtocol:
    """
    Encodes and decodes packets according to the Smart Helmet binary protocol.

    Responsibilities
    ----------------
    - Build well-formed 8-byte packets from typed parameters.
    - Validate and parse raw 8-byte buffers back into :class:`Packet` objects.
    - Compute and verify the single-byte XOR checksum.
    - Raise :class:`ProtocolError` on malformed or corrupt packets.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(
        self,
        packet_type: PacketType,
        sequence_number: int,
        payload: bytes = b"\x00\x00\x00",
    ) -> bytes:
        """
        Encode a packet into 8 raw bytes ready for transmission.

        Parameters
        ----------
        packet_type:
            The :class:`PacketType` code.
        sequence_number:
            Rolling counter 0–65535.
        payload:
            Exactly 3 bytes of payload data (zero-padded if shorter).

        Raises
        ------
        ProtocolError
            If *payload* exceeds 3 bytes or *sequence_number* is out of range.
        """
        if len(payload) > 3:
            raise ProtocolError("Payload must not exceed 3 bytes")
        if not 0 <= sequence_number <= 0xFFFF:
            raise ProtocolError("Sequence number out of range (0–65535)")

        payload = payload.ljust(3, b"\x00")[:3]
        header = bytes([
            MAGIC_BYTE,
            packet_type.value,
            (sequence_number >> 8) & 0xFF,
            sequence_number & 0xFF,
        ])
        body = header + payload
        checksum = self._xor_checksum(body)
        return body + bytes([checksum])

    def decode(self, raw: bytes) -> Packet:
        """
        Parse an 8-byte raw buffer into a :class:`Packet`.

        Raises
        ------
        ProtocolError
            If the buffer length is wrong, the magic byte is missing, or
            the checksum does not match.
        """
        if len(raw) != PACKET_SIZE:
            raise ProtocolError(
                f"Expected {PACKET_SIZE} bytes, got {len(raw)}"
            )
        if raw[0] != MAGIC_BYTE:
            raise ProtocolError(
                f"Bad magic byte: 0x{raw[0]:02X} (expected 0x{MAGIC_BYTE:02X})"
            )

        expected_checksum = self._xor_checksum(raw[:-1])
        if raw[-1] != expected_checksum:
            raise ProtocolError(
                f"Checksum mismatch: got 0x{raw[-1]:02X}, "
                f"expected 0x{expected_checksum:02X}"
            )

        try:
            packet_type = PacketType(raw[1])
        except ValueError:
            raise ProtocolError(f"Unknown packet type: 0x{raw[1]:02X}")

        sequence_number = (raw[2] << 8) | raw[3]
        payload = raw[4:7]
        return Packet(packet_type=packet_type, sequence_number=sequence_number, payload=payload)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _xor_checksum(data: bytes) -> int:
        result = 0
        for byte in data:
            result ^= byte
        return result


class ProtocolError(Exception):
    """Raised when a packet fails validation."""
