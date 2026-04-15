# ESP32 LED Helmet Setup (Beginner-Friendly)

This guide helps you build, upload, and test a helmet LED navigation prototype using:
- ESP32 DevKit board
- Breadboard
- 6 green LEDs
- 6 yellow LEDs
- 12 resistors (220 ohm to 470 ohm)
- Jumper wires
- Laptop (Windows)

## 1) What this prototype does

1. Laptop (or app later) sends cue commands over BLE to ESP32.
2. ESP32 receives commands and drives LED patterns.
3. LEDs indicate LEFT / RIGHT / PREPARE / NOW / MISSED states.

For now, mobile app is not required. You can test from laptop scripts.

## 2) Safety and hardware basics

1. Use one resistor per LED. Never connect LED directly to GPIO.
2. ESP32 GPIO is 3.3V logic. Keep currents low.
3. Always share ground for all LEDs and ESP32.
4. Prototype on breadboard before helmet mounting.

## 3) LED layout plan (12 LEDs)

Use 2 side clusters (left and right), each with:
- 3 yellow LEDs
- 3 green LEDs

Recommended meaning:
- Yellow: warning / upcoming / missed turn
- Green: immediate turn action

## 4) Exact pin mapping used by firmware

Firmware file: `embedded/esp32_firmware/smart_helmet_ble_led.ino`

### Left side
- Left Yellow 1 -> GPIO 16
- Left Yellow 2 -> GPIO 17
- Left Yellow 3 -> GPIO 18
- Left Green 1  -> GPIO 19
- Left Green 2  -> GPIO 21
- Left Green 3  -> GPIO 22

### Right side
- Right Yellow 1 -> GPIO 23
- Right Yellow 2 -> GPIO 25
- Right Yellow 3 -> GPIO 26
- Right Green 1  -> GPIO 27
- Right Green 2  -> GPIO 32
- Right Green 3  -> GPIO 33

## 5) Circuit wiring (step-by-step)

For each of the 12 LEDs:
1. Identify LED legs:
   - Longer leg = anode (+)
   - Shorter leg = cathode (-)
2. Connect one resistor from selected GPIO pin to LED anode.
3. Connect LED cathode to GND rail on breadboard.

Common power/ground:
1. Connect ESP32 GND pin to breadboard GND rail.
2. Use this same GND rail for all LED cathodes.

Tip:
- Start with only 2 LEDs first (one left, one right), verify command control, then wire all 12.

## 6) Upload firmware to ESP32 (Arduino IDE)

### 6.1 Install Arduino IDE
- Download and install Arduino IDE 2.x.

### 6.2 Add ESP32 board support
1. Open Arduino IDE.
2. Go to File -> Preferences.
3. In Additional boards manager URLs, add:
   - `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
4. Open Boards Manager.
5. Search `esp32` and install `esp32 by Espressif Systems`.

### 6.3 Select board and port
1. Tools -> Board -> ESP32 Arduino -> `ESP32 Dev Module` (or your exact board).
2. Tools -> Port -> select your ESP32 COM port.

### 6.4 Open firmware
1. Open file `embedded/esp32_firmware/smart_helmet_ble_led.ino` in Arduino IDE.
2. Click Verify.
3. Click Upload.

### 6.5 Confirm serial output
1. Open Serial Monitor at 115200 baud.
2. You should see BLE status lines such as advertising/connected.

## 7) BLE command protocol

Device name: `SmartHelmet-ESP32`

Supported commands:
- `CLEAR`
- `LEFT_PREPARE`
- `LEFT_NOW`
- `LEFT_MISSED`
- `RIGHT_PREPARE`
- `RIGHT_NOW`
- `RIGHT_MISSED`
- `HAZARD`
- `ARRIVED`
- `PING`

## 8) Laptop setup to send commands manually

Scripts folder: `embedded/tools`

### 8.1 Install Python dependencies
From repo root:

```powershell
python -m pip install -r embedded/tools/requirements.txt
```

### 8.2 Scan for BLE devices

```powershell
python embedded/tools/ble_scan.py
```

Find `SmartHelmet-ESP32` and note address (optional).

### 8.3 Send one command
By device name:

```powershell
python embedded/tools/ble_send_command.py --command LEFT_PREPARE
```

By explicit BLE address:

```powershell
python embedded/tools/ble_send_command.py --address XX:XX:XX:XX:XX:XX --command RIGHT_NOW
```

Clear LEDs:

```powershell
python embedded/tools/ble_send_command.py --command CLEAR
```

## 9) Test using NCS from laptop (before mobile app)

You can bridge NCS UI state -> BLE commands.

### 9.1 Start NCS API server

```powershell
uvicorn navigation.server:app --host 0.0.0.0 --port 8000
```

### 9.2 Start navigation session in NCS
Use any REST client or PowerShell:

```powershell
$body = @{
  session_id = "ride_demo_1"
  ts_ms = [int64]([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds())
  action_type = "START_NAVIGATION"
  payload = @{ origin = "A"; destination = "B" }
  route_data = @{
    origin = @{ lat = 19.076; lon = 72.877; label = "Start" }
    destination = @{ lat = 19.100; lon = 72.900; label = "End" }
    steps = @(
      @{ lat = 19.078; lon = 72.879; instruction = "Turn right"; distance = 300 },
      @{ lat = 19.085; lon = 72.885; instruction = "Turn left"; distance = 120 }
    )
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/navigation/ui/action" -Body $body -ContentType "application/json"
```

### 9.3 Run NCS -> BLE bridge

```powershell
python embedded/tools/ncs_ble_bridge.py --session-id ride_demo_1
```

Optional explicit address:

```powershell
python embedded/tools/ncs_ble_bridge.py --session-id ride_demo_1 --address XX:XX:XX:XX:XX:XX
```

### 9.4 Observe behavior
- Bridge polls `/api/navigation/ui/state`.
- It maps instruction + distance to commands (`LEFT_PREPARE`, `LEFT_NOW`, etc).
- Commands are sent to ESP32 over BLE.

## 10) Understanding LED behavior in firmware

1. `LEFT_PREPARE` / `RIGHT_PREPARE`
- Yellow LEDs on that side blink slowly.

2. `LEFT_NOW` / `RIGHT_NOW`
- Yellow side stays on.
- Green side chases quickly.

3. `LEFT_MISSED` / `RIGHT_MISSED`
- Yellow side blinks rapidly.

4. `HAZARD`
- Both yellow sides blink rapidly.

5. `ARRIVED`
- Both green sides pulse.

6. `CLEAR`
- All LEDs off.

## 11) Troubleshooting

1. ESP32 not visible in scan:
- Check USB power.
- Reopen Serial Monitor and verify BLE advertising log.
- Restart ESP32 and scan again.

2. Connection fails on Windows:
- Make sure no other app is connected to ESP32 BLE.
- Toggle laptop Bluetooth off/on.

3. LEDs not lighting:
- Verify LED polarity.
- Verify each LED has resistor.
- Verify GPIO pin mapping exactly.
- Test with manual command script first.

4. Bridge runs but no obvious cue change:
- Check NCS UI state payload for `next_instruction_text` and `distance_to_next_m`.
- Use manual commands to confirm hardware path first.

## 12) Next improvements (after this prototype)

1. Add transistor or LED driver if you increase brightness/current.
2. Add battery module and switch for wearable deployment.
3. Add waterproof sleeve and secure wire routing on helmet.
4. Add acknowledgment command from ESP32 back to app/NCS for reliability.
