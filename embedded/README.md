# Embedded Systems & Application Interface Module

**Owner:** Priyal Jain

---

## Purpose

This module has two closely related responsibilities:

1. **Helmet-side firmware** – controls the physical components mounted on the
   helmet (LEDs, Bluetooth radio, onboard instruction decoder).
2. **App-side interface** – provides the mobile app's user interface logic
   for displaying navigation information to the rider and managing the BLE
   connection to the helmet.

---

## File Layout

```
embedded/
├── bluetooth_comm.py        # BLE connection management
├── led_controller.py        # LED pattern logic
├── instruction_parser.py    # Binary/text packet decoder
└── app_interface/
    ├── ui_manager.py        # Navigation display state
    └── device_manager.py    # Helmet discovery & pairing lifecycle
```

---

## How It Works

### Helmet Side

1. **Bluetooth** – `BluetoothComm` keeps the BLE link alive between the phone
   and helmet.  It scans for the helmet, connects, and forwards incoming data
   bytes to registered callbacks.  If the link drops, the communication module
   attempts a reconnect automatically.

2. **Instruction Parser** – `InstructionParser.parse()` decodes a 5-byte
   packet sent from the phone into a `ParsedInstruction`.  The packet contains
   a one-byte action code (e.g. `TURN_LEFT = 0x01`) and a 2-byte distance
   field.  This tiny packet format keeps bandwidth usage minimal.

3. **LED Controller** – `LEDController.instruction_to_led()` maps each
   `ParsedInstruction` to a visual pattern:

   | Event | LED Pattern |
   |-------|-------------|
   | Turn left | Blink left |
   | Turn right | Blink right |
   | U-turn / Arrive | Blink both |
   | GPS lost | Solid red |
   | Crash / SOS | Rapid red |
   | BT connected | Solid blue |

### App Side

4. **UI Manager** – `UIManager` holds a `NavDisplay` data object that the
   app's rendering layer reads on every frame.  Helper methods like
   `update_instruction()`, `update_speed()`, and `show_crash_alert()` keep
   the display state current.

5. **Device Manager** – `DeviceManager` wraps `BluetoothComm` to add
   helmet-specific logic: filtering scan results by device name prefix,
   remembering the last paired address, and triggering callbacks when the
   helmet connects or drops.

---

## Key Classes

### `BluetoothComm`
- `scan(timeout_seconds)` → `list[str]`
- `connect(address)` → `bool`
- `disconnect()`
- `send(data: bytes)` → `bool`

### `InstructionParser`
- `parse(packet: bytes)` → `ParsedInstruction`
- `encode(instruction: ParsedInstruction)` → `bytes`

### `LEDController`
- `apply_pattern(pattern: LEDPattern)`
- `instruction_to_led(instruction: str)` → `LEDPattern`
- `turn_off()`

### `UIManager`
- `update_instruction(instruction, distance_meters)`
- `update_speed(speed_kph)`
- `update_gps_status(active: bool)`
- `update_heading(heading_degrees)`
- `show_crash_alert()`
- `get_display()` → `NavDisplay`

### `DeviceManager`
- `scan_for_helmets()` → `list[HelmetDevice]`
- `connect(device: HelmetDevice)` → `bool`
- `disconnect()`
- `reconnect()` → `bool`

---

## Dependencies

- Python standard library only (`enum`, `dataclasses`).
- In production: `bleak` (cross-platform BLE library) for `BluetoothComm`.
