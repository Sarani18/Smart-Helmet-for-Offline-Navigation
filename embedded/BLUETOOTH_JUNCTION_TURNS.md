# Bluetooth Junction Turn Streaming

This path sends the same instruction shown on the embedded map UI to the ESP32
over the existing embedded Bluetooth Serial firmware.

It does not use `navigation.hardware_service` or the navigation module's
Bluetooth connection.

## Code Path

- Map instruction source: `UIStateMessage.next_instruction_text`
- Embedded receiver: `embedded.websocket_server.receive_ui_state`
- Bridge: `embedded.ui_bridge.UIBridge.on_ui_state`
- Bluetooth sender: `embedded.bluetooth_instruction_bridge.BluetoothInstructionBridge`
- ESP firmware: `smart_helmet_bluetooth_led/smart_helmet_bluetooth_led.ino`

## Instruction Mapping

The bridge translates the current map instruction text into the ESP text
protocol:

| Map instruction / state | ESP command |
| --- | --- |
| contains `left` | `LEFT` |
| contains `right` | `RIGHT` |
| straight/continue/default | `STRAIGHT` |
| off-route or `PositionMode.UNKNOWN` | `HAZARD` |
| crash/SOS text | `SOS_ON` |
| destination reached/arrived | `ARRIVED` |

Duplicate commands are suppressed, so repeated `STRAIGHT` updates at 2-5 Hz do
not spam the ESP.

## ESP32 Setup

1. Open `smart_helmet_bluetooth_led/smart_helmet_bluetooth_led.ino` in Arduino
   IDE.
2. Select an ESP32 board and upload the sketch.
3. Open Windows Bluetooth settings and pair the device named
   `SmartHelmet-LED`.
4. Find the paired outgoing COM port in Device Manager. Example: `COM6`.

## Python Setup

Install runtime dependencies:

```powershell
python -m pip install fastapi uvicorn pyserial requests
```

Set the ESP Bluetooth Serial port before starting the embedded server:

```powershell
$env:SMART_HELMET_BT_PORT="COM6"
$env:SMART_HELMET_BT_BAUD="115200"
python -m embedded.websocket_server
```

Open the map UI:

```text
http://localhost:8765/
```

## Real-Time Route Test

In another terminal, stream the sample CV/DR-style map updates:

```powershell
python embedded/test_input.py
```

As each junction instruction is rendered on the map, the bridge sends the
matching command to the ESP. Terminal logs look like:

```text
[ui-sync] state->bt queued instruction='Turn right onto NH-48...' command=RIGHT
[ui-sync] bt->esp command=RIGHT status=sent
```

Check current Bluetooth status:

```powershell
Invoke-RestMethod http://localhost:8765/status
```

## One-Command Hardware Check

To verify the ESP firmware and COM port without running the map:

```powershell
python esp32_bluetooth_sender.py --port COM6 send LEFT
python esp32_bluetooth_sender.py --port COM6 send RIGHT
python esp32_bluetooth_sender.py --port COM6 send STRAIGHT
```
