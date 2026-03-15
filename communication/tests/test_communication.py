"""
Unit tests for the Communication Protocol, Packet Handler, and Sync Manager.
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from communication.protocol import SmartHelmetProtocol, PacketType, Packet, ProtocolError
from communication.packet_handler import PacketHandler
from communication.sync_manager import SyncManager


# ---------------------------------------------------------------------------
# SmartHelmetProtocol tests
# ---------------------------------------------------------------------------

class TestSmartHelmetProtocol(unittest.TestCase):

    def setUp(self):
        self.proto = SmartHelmetProtocol()

    def test_encode_returns_8_bytes(self):
        raw = self.proto.encode(PacketType.HEARTBEAT, 0)
        self.assertEqual(len(raw), 8)

    def test_encode_decode_roundtrip(self):
        payload = b"\x01\x02\x03"
        raw = self.proto.encode(PacketType.NAV_INSTRUCTION, 42, payload)
        packet = self.proto.decode(raw)
        self.assertEqual(packet.packet_type, PacketType.NAV_INSTRUCTION)
        self.assertEqual(packet.sequence_number, 42)
        self.assertEqual(packet.payload, payload)

    def test_decode_wrong_length_raises(self):
        with self.assertRaises(ProtocolError):
            self.proto.decode(b"\xAB\x01\x00\x00")

    def test_decode_bad_magic_raises(self):
        raw = self.proto.encode(PacketType.HEARTBEAT, 0)
        corrupted = b"\x00" + raw[1:]
        with self.assertRaises(ProtocolError):
            self.proto.decode(corrupted)

    def test_decode_bad_checksum_raises(self):
        raw = bytearray(self.proto.encode(PacketType.HEARTBEAT, 0))
        raw[-1] ^= 0xFF  # flip checksum bits
        with self.assertRaises(ProtocolError):
            self.proto.decode(bytes(raw))

    def test_decode_unknown_type_raises(self):
        raw = bytearray(self.proto.encode(PacketType.HEARTBEAT, 0))
        raw[1] = 0x99  # unknown type code
        # Recompute checksum
        xor = 0
        for b in raw[:-1]:
            xor ^= b
        raw[-1] = xor
        with self.assertRaises(ProtocolError):
            self.proto.decode(bytes(raw))

    def test_payload_too_long_raises(self):
        with self.assertRaises(ProtocolError):
            self.proto.encode(PacketType.HEARTBEAT, 0, b"\x01\x02\x03\x04")

    def test_sequence_number_out_of_range_raises(self):
        with self.assertRaises(ProtocolError):
            self.proto.encode(PacketType.HEARTBEAT, 70000)

    def test_sequence_wraps_in_range(self):
        raw = self.proto.encode(PacketType.HEARTBEAT, 0xFFFF)
        packet = self.proto.decode(raw)
        self.assertEqual(packet.sequence_number, 0xFFFF)


# ---------------------------------------------------------------------------
# PacketHandler tests
# ---------------------------------------------------------------------------

class TestPacketHandler(unittest.TestCase):

    def setUp(self):
        self.proto = SmartHelmetProtocol()
        self.handler = PacketHandler(self.proto, max_retries=2)

    def test_enqueue_adds_to_queue(self):
        self.handler.enqueue(PacketType.HEARTBEAT)
        self.assertEqual(self.handler.queue_size, 1)

    def test_dequeue_removes_from_queue(self):
        self.handler.enqueue(PacketType.HEARTBEAT)
        raw = self.handler.dequeue()
        self.assertIsNotNone(raw)
        self.assertEqual(self.handler.queue_size, 0)

    def test_dequeue_empty_returns_none(self):
        self.assertIsNone(self.handler.dequeue())

    def test_handle_incoming_dispatches_handler(self):
        received = []
        self.handler.register_handler(PacketType.HEARTBEAT, lambda p: received.append(p))
        raw = self.proto.encode(PacketType.HEARTBEAT, 10)
        self.handler.handle_incoming(raw)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].sequence_number, 10)

    def test_handle_incoming_auto_acks(self):
        raw = self.proto.encode(PacketType.GPS_STATUS, 5, b"\x01\x00\x00")
        self.handler.handle_incoming(raw)
        # An ACK should be queued
        self.assertGreater(self.handler.queue_size, 0)

    def test_duplicate_packet_ignored(self):
        received = []
        self.handler.register_handler(PacketType.HEARTBEAT, lambda p: received.append(p))
        raw = self.proto.encode(PacketType.HEARTBEAT, 7)
        self.handler.handle_incoming(raw)
        self.handler.handle_incoming(raw)  # same sequence number
        self.assertEqual(len(received), 1)

    def test_retry_pending_requeues(self):
        # Enqueue a non-ACK packet; it should appear in pending_acks
        self.handler.enqueue(PacketType.NAV_INSTRUCTION, b"\x01\x00\x00")
        # Clear send queue manually
        self.handler.dequeue()
        self.assertEqual(self.handler.queue_size, 0)
        retried = self.handler.retry_pending()
        self.assertEqual(retried, 1)
        self.assertEqual(self.handler.queue_size, 1)

    def test_retry_drops_after_max_retries(self):
        self.handler.enqueue(PacketType.NAV_INSTRUCTION, b"\x01\x00\x00")
        self.handler.dequeue()
        self.handler.retry_pending()
        self.handler.dequeue()
        self.handler.retry_pending()  # retry 2 – hits max_retries=2
        self.handler.dequeue()
        retried = self.handler.retry_pending()  # should drop
        self.assertEqual(retried, 0)
        self.assertEqual(self.handler.pending_ack_count, 0)

    def test_handle_corrupted_returns_none(self):
        result = self.handler.handle_incoming(b"\xFF\xFF\xFF\xFF\xFF\xFF\xFF\xFF")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# SyncManager tests
# ---------------------------------------------------------------------------

class TestSyncManager(unittest.TestCase):

    def setUp(self):
        self.proto = SmartHelmetProtocol()
        self.pkt_handler = PacketHandler(self.proto)
        self.sync = SyncManager(self.pkt_handler, self.proto)

    def test_notify_gps_change_enqueues_packet(self):
        initial_size = self.pkt_handler.queue_size
        self.sync.notify_gps_change(False)
        self.assertGreater(self.pkt_handler.queue_size, initial_size)

    def test_notify_gps_no_change_no_packet(self):
        # GPS is already True (default); notify True again → no packet
        initial_size = self.pkt_handler.queue_size
        self.sync.notify_gps_change(True)
        self.assertEqual(self.pkt_handler.queue_size, initial_size)

    def test_gps_change_fires_callback(self):
        events = []
        self.sync.register_gps_change_callback(lambda v: events.append(v))
        self.sync.notify_gps_change(False)
        self.assertEqual(events, [False])

    def test_update_speed_enqueues_packet(self):
        initial_size = self.pkt_handler.queue_size
        self.sync.update_speed(60.0)
        self.assertGreater(self.pkt_handler.queue_size, initial_size)

    def test_get_state_returns_state(self):
        state = self.sync.get_state()
        self.assertTrue(state.gps_active)

    def test_tick_sends_heartbeat(self):
        # Force the heartbeat to fire on the next tick
        self.sync._last_heartbeat_sent = 0.0
        self.sync.tick()
        # A heartbeat packet should have been enqueued
        found_heartbeat = False
        while True:
            raw = self.pkt_handler.dequeue()
            if raw is None:
                break
            packet = self.proto.decode(raw)
            if packet.packet_type == PacketType.HEARTBEAT:
                found_heartbeat = True
                break
        self.assertTrue(found_heartbeat)


if __name__ == "__main__":
    unittest.main()
