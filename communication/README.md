# Communication Protocol, Application Integration & Performance Optimization Module

**Owner:** Jinesh Nanal

---

## Purpose

This module is the "nervous system" of the Smart Helmet project.  It defines
exactly *how* the mobile app and the helmet talk to each other, ensures that
messages are delivered reliably even over a noisy Bluetooth link, keeps both
sides in sync, and provides the tools for measuring system performance.

---

## Files

| File | Responsibility |
|------|---------------|
| `protocol.py` | Binary packet format definition – encode / decode / checksum |
| `packet_handler.py` | Send/receive queues, duplicate detection, ACK tracking, retry logic |
| `sync_manager.py` | Heartbeat, GPS-mode change notifications, link health monitoring |

---

## Packet Format

Every message between the app and the helmet is exactly **8 bytes**:

```
Byte 0 : Magic byte  (0xAB) – identifies a valid Smart Helmet packet
Byte 1 : Packet type (e.g. 0x01 = NAV_INSTRUCTION, 0x10 = IMU_DATA)
Byte 2 : Sequence high byte  ┐
Byte 3 : Sequence low byte   ┘ → rolling counter 0–65535
Byte 4 : Payload byte 0      ┐
Byte 5 : Payload byte 1      │ → type-specific data
Byte 6 : Payload byte 2      ┘
Byte 7 : XOR checksum of bytes 0–6
```

The compact 8-byte design keeps Bluetooth latency low while still providing
basic integrity checking via the XOR checksum.

---

## How It Works (Step by Step)

1. **Encoding** – The app calls `SmartHelmetProtocol.encode()` with a
   `PacketType`, a rolling sequence number, and up to 3 bytes of payload.
   The protocol object builds the 8-byte buffer and appends the checksum.

2. **Queueing** – The encoded bytes are passed to `PacketHandler.enqueue()`,
   which appends them to an outbound queue.  The link layer (Bluetooth) drains
   the queue by calling `PacketHandler.dequeue()`.

3. **Receiving** – When raw bytes arrive from the helmet,
   `PacketHandler.handle_incoming()` validates and decodes them.  It checks
   for duplicate sequence numbers (discards repeated packets) and dispatches
   the decoded packet to the registered type handler.

4. **Acknowledgement** – For every non-ACK packet received, an ACK packet is
   automatically enqueued.  On the sender side, `PacketHandler.retry_pending()`
   re-enqueues any packet whose ACK has not arrived after a tick.  A packet is
   discarded after 3 failed retries.

5. **Heartbeat** – `SyncManager.tick()` (called every second) sends a
   `HEARTBEAT` packet every 2 seconds.  If no heartbeat reply is received
   within 6 seconds, the link is declared unhealthy and the reconnect callback
   is fired.

6. **GPS mode switching** – When the localization module loses or restores
   GPS, it calls `SyncManager.notify_gps_change()`.  This encodes a
   `GPS_STATUS` packet so the helmet LED changes colour immediately.

---

## Packet Types

| Code | Name | Direction | Meaning |
|------|------|-----------|---------|
| 0x01 | NAV_INSTRUCTION | App → Helmet | Turn instruction + distance |
| 0x02 | GPS_STATUS | App → Helmet | GPS active (1) or lost (0) |
| 0x03 | SPEED_UPDATE | App → Helmet | Current speed in 0.1 km/h units |
| 0x10 | IMU_DATA | Helmet → App | Raw sensor reading |
| 0x11 | BATTERY_LEVEL | Helmet → App | Battery percentage |
| 0x12 | ACK | Both | Acknowledgement |
| 0x20 | CRASH_EVENT | Both | Crash detected |
| 0x21 | SOS_CONFIRM | Both | SOS acknowledged |
| 0xFE | HEARTBEAT | Both | Link keep-alive |
| 0xFF | RESET | Both | Request full reset |

---

## Key Classes

### `SmartHelmetProtocol`
- `encode(packet_type, sequence_number, payload)` → `bytes`
- `decode(raw: bytes)` → `Packet`

### `PacketHandler`
- `register_handler(packet_type, callback)`
- `enqueue(packet_type, payload)` → `int` (seq num)
- `dequeue()` → `bytes | None`
- `handle_incoming(raw: bytes)` → `Packet | None`
- `retry_pending()` → `int`

### `SyncManager`
- `tick()` – call every second
- `notify_gps_change(gps_active: bool)`
- `update_speed(speed_kph: float)`
- `get_state()` → `SystemState`

---

## Dependencies

- Python standard library only (`enum`, `collections`, `time`, `dataclasses`).
