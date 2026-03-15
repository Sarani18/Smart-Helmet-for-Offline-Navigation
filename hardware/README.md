# Hardware Integration Module

> **Status: Placeholder — software-first phase**
>
> Hardware integration is planned for a future project phase.  This module
> defines the *expected interfaces* so that the software modules can be
> written and tested independently of physical hardware.

---

## Purpose

This module is the bridge between the software stack and the helmet's
physical components.  All other modules (navigation, localization, embedded,
communication) interact with hardware only through this interface, making it
easy to swap in a real driver without changing any other code.

---

## File

| File | Responsibility |
|------|---------------|
| `hardware_interface.py` | Stub class defining `initialize`, `read_sensors`, `write_display`, `set_led`, `shutdown` |

---

## Expected Physical Components

| Component | Role |
|-----------|------|
| IMU (e.g. MPU-6050) | Provides accelerometer and gyroscope data to the localization module |
| Forward-facing camera (e.g. OV2640) | Captures frames for obstacle / environment monitoring |
| HUD / display (e.g. small OLED) | Shows turn instructions, speed, and GPS status |
| RGB status LEDs | Give the rider at-a-glance direction and status feedback |
| Compact MCU (e.g. ESP32 / RPi Zero 2W) | Runs the embedded firmware and bridges hardware to the phone |
| Power management IC | Monitors battery level; enables safe shutdown |
| Local flash storage | Persists offline map tiles and system event logs |

---

## How to Extend

1. Create a subclass of `HardwareInterface` in this module.
2. Override the stub methods with real GPIO / SPI / I²C calls.
3. Pass your subclass instance to the `app/main.py` initializer.

The software modules will continue to work without any changes.

---

## Key Class

### `HardwareInterface`
- `initialize()` → `bool`
- `read_sensors()` → `HardwareSensorData`
- `write_display(text, line)`
- `set_led(pattern_code)`
- `shutdown()`
- `get_battery_level()` → `int`

---

## Dependencies

- Python standard library only (`dataclasses`, `time`).
- Production implementation will require hardware-specific libraries
  (e.g. `smbus2` for I²C, `RPi.GPIO`, `picamera2`).
