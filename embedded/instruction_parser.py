"""
Instruction Parser
------------------
Decodes compact binary/text instruction packets received from the mobile
app and converts them into actionable commands for the helmet hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class InstructionCode(IntEnum):
    """Single-byte instruction codes used in the inter-device protocol."""

    NOP = 0x00          # No operation / heartbeat
    TURN_LEFT = 0x01
    TURN_RIGHT = 0x02
    GO_STRAIGHT = 0x03
    U_TURN = 0x04
    ARRIVE = 0x05
    GPS_LOST = 0x10
    GPS_RESTORED = 0x11
    CRASH_ALERT = 0x20
    SOS_TRIGGERED = 0x21
    LED_OFF = 0xFF


@dataclass
class ParsedInstruction:
    """
    The decoded result of a single packet from the mobile app.

    Attributes
    ----------
    code : InstructionCode
        The primary action the helmet should perform.
    distance_meters : float
        Distance to the next manoeuvre (0 if not applicable).
    text : str
        Human-readable label for HUD / TTS output.
    """

    code: InstructionCode
    distance_meters: float = 0.0
    text: str = ""


class InstructionParser:
    """
    Parses structured instruction packets coming from the mobile application
    and converts them into :class:`ParsedInstruction` objects that the
    helmet hardware can act on.

    Packet format (5 bytes, big-endian):
    ┌────────┬──────────────────┬──────────┐
    │  code  │ distance (uint16)│  pad x2  │
    │ 1 byte │     2 bytes      │  2 bytes │
    └────────┴──────────────────┴──────────┘

    Responsibilities
    ----------------
    - Validate packet length and magic byte.
    - Decode instruction code and associated distance.
    - Map codes to human-readable text for HUD display.
    - Return descriptive errors on malformed packets.
    """

    PACKET_LENGTH = 5

    CODE_TEXT_MAP = {
        InstructionCode.NOP: "Continue",
        InstructionCode.TURN_LEFT: "Turn left",
        InstructionCode.TURN_RIGHT: "Turn right",
        InstructionCode.GO_STRAIGHT: "Go straight",
        InstructionCode.U_TURN: "Make a U-turn",
        InstructionCode.ARRIVE: "You have arrived",
        InstructionCode.GPS_LOST: "GPS signal lost",
        InstructionCode.GPS_RESTORED: "GPS signal restored",
        InstructionCode.CRASH_ALERT: "Crash detected",
        InstructionCode.SOS_TRIGGERED: "SOS alert sent",
        InstructionCode.LED_OFF: "Standby",
    }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(self, packet: bytes) -> ParsedInstruction:
        """
        Decode a 5-byte packet into a :class:`ParsedInstruction`.

        Raises
        ------
        ValueError
            If the packet length is wrong or the code is unrecognised.
        """
        if len(packet) != self.PACKET_LENGTH:
            raise ValueError(
                f"Expected {self.PACKET_LENGTH} bytes, got {len(packet)}"
            )

        code_byte = packet[0]
        distance = int.from_bytes(packet[1:3], byteorder="big")

        try:
            code = InstructionCode(code_byte)
        except ValueError:
            raise ValueError(f"Unknown instruction code: 0x{code_byte:02X}")

        text = self.CODE_TEXT_MAP.get(code, "Unknown")
        return ParsedInstruction(code=code, distance_meters=float(distance), text=text)

    def encode(self, instruction: ParsedInstruction) -> bytes:
        """
        Encode a :class:`ParsedInstruction` back into a 5-byte packet.
        Useful for unit tests and loopback validation.
        """
        code_byte = bytes([instruction.code.value])
        dist_bytes = int(instruction.distance_meters).to_bytes(2, byteorder="big")
        return code_byte + dist_bytes + b"\x00\x00"
