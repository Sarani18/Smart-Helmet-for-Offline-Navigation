"""
Packet Handler
--------------
Buffers, queues, and dispatches packets on both the send and receive paths,
and handles transmission errors and retries.
"""

from __future__ import annotations

from collections import deque
from typing import Callable, Deque, Dict, Optional

from .protocol import Packet, PacketType, ProtocolError, SmartHelmetProtocol


class PacketHandler:
    """
    Manages the send/receive queues and error-recovery logic for the
    inter-device communication link.

    Responsibilities
    ----------------
    - Maintain an outbound queue of packets waiting to be sent.
    - Parse incoming raw bytes and dispatch decoded packets to registered
      type-specific handlers.
    - Track which sequence numbers have been acknowledged.
    - Retry unacknowledged packets up to *max_retries* times.
    - Discard duplicate packets (same sequence number received twice).
    """

    def __init__(
        self,
        protocol: Optional[SmartHelmetProtocol] = None,
        max_retries: int = 3,
    ) -> None:
        self._protocol = protocol or SmartHelmetProtocol()
        self._max_retries = max_retries
        self._send_queue: Deque[bytes] = deque()
        self._pending_acks: Dict[int, tuple] = {}   # seq_num → (raw_bytes, retry_count)
        self._seen_sequences: set = set()
        self._handlers: Dict[PacketType, Callable[[Packet], None]] = {}
        self._sequence_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_handler(
        self, packet_type: PacketType, handler: Callable[[Packet], None]
    ) -> None:
        """
        Register a callback function that is called whenever a packet of
        *packet_type* arrives.
        """
        self._handlers[packet_type] = handler

    def enqueue(self, packet_type: PacketType, payload: bytes = b"") -> int:
        """
        Build a packet and add it to the outbound queue.

        Returns the assigned sequence number.
        """
        seq = self._next_sequence()
        raw = self._protocol.encode(packet_type, seq, payload)
        self._send_queue.append(raw)
        if packet_type != PacketType.ACK:
            self._pending_acks[seq] = (raw, 0)
        return seq

    def dequeue(self) -> Optional[bytes]:
        """
        Remove and return the next raw packet from the outbound queue, or
        *None* if the queue is empty.
        """
        if self._send_queue:
            return self._send_queue.popleft()
        return None

    def handle_incoming(self, raw: bytes) -> Optional[Packet]:
        """
        Parse *raw* and invoke the registered handler for its type.

        Automatically sends an ACK for every non-ACK packet received.

        Returns the decoded :class:`Packet` or *None* on parse error.
        """
        try:
            packet = self._protocol.decode(raw)
        except ProtocolError:
            return None

        # Duplicate detection
        if packet.sequence_number in self._seen_sequences:
            return packet  # silently drop duplicate
        self._seen_sequences.add(packet.sequence_number)

        # Dispatch to handler
        handler = self._handlers.get(packet.packet_type)
        if handler:
            handler(packet)

        # Acknowledge non-ACK packets
        if packet.packet_type != PacketType.ACK:
            self.enqueue(PacketType.ACK, bytes([packet.sequence_number >> 8,
                                                packet.sequence_number & 0xFF,
                                                0x00]))
        else:
            # Clear from pending-ack list
            ack_seq = (packet.payload[0] << 8) | packet.payload[1]
            self._pending_acks.pop(ack_seq, None)

        return packet

    def retry_pending(self) -> int:
        """
        Re-enqueue all unacknowledged packets that have not exceeded the retry
        limit.  Packets that reach *max_retries* are dropped.

        Returns the number of packets re-enqueued.
        """
        to_remove = []
        retried = 0
        for seq, (raw, count) in self._pending_acks.items():
            if count >= self._max_retries:
                to_remove.append(seq)
            else:
                self._send_queue.append(raw)
                self._pending_acks[seq] = (raw, count + 1)
                retried += 1
        for seq in to_remove:
            del self._pending_acks[seq]
        return retried

    @property
    def queue_size(self) -> int:
        """Number of packets currently in the outbound queue."""
        return len(self._send_queue)

    @property
    def pending_ack_count(self) -> int:
        """Number of sent packets still awaiting acknowledgement."""
        return len(self._pending_acks)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _next_sequence(self) -> int:
        seq = self._sequence_counter
        self._sequence_counter = (self._sequence_counter + 1) % 0x10000
        return seq
