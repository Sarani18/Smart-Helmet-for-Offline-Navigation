"""
Hardware Interface
------------------
Abstract interface (stub) for all helmet-mounted hardware components.

This file defines the expected API that hardware driver implementations
must satisfy.  It is intentionally minimal – the focus at this stage is
on the software modules.  Hardware integration will be built on top of
these stubs in the next project phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class HardwareSensorData:
    """
    Container for a single snapshot of all sensor readings from the helmet.

    Attributes
    ----------
    accel_x, accel_y, accel_z : float
        Linear acceleration in m/s² (from IMU).
    gyro_x, gyro_y, gyro_z : float
        Angular velocity in degrees/second (from IMU).
    camera_frame : bytes | None
        Raw camera frame bytes (JPEG or raw), or *None* if camera is inactive.
    battery_percent : int
        Battery charge level 0–100.
    timestamp : float
        Unix timestamp of this reading.
    """

    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 9.81   # default: at rest, z ≈ g
    gyro_x: float = 0.0
    gyro_y: float = 0.0
    gyro_z: float = 0.0
    camera_frame: Optional[bytes] = None
    battery_percent: int = 100
    timestamp: float = 0.0


class HardwareInterface:
    """
    Stub interface for the helmet's physical hardware.

    Production implementations will subclass this and override each method
    to communicate with the actual MCU, camera, and display hardware.

    Expected hardware components (high-level):
    ------------------------------------------
    - IMU (accelerometer + gyroscope) – e.g. MPU-6050
    - Forward-facing camera module – e.g. OV2640
    - HUD / visor display – e.g. small OLED or waveguide projection
    - RGB status LEDs
    - Compact processing unit – e.g. ESP32 / Raspberry Pi Zero 2W
    - Battery + power management IC
    - Local flash storage for map tiles and logs
    """

    def initialize(self) -> bool:
        """
        Initialize all hardware peripherals.

        Returns
        -------
        bool
            *True* if all components initialized successfully.
        """
        # TODO: implement MCU startup sequence
        return True

    def read_sensors(self) -> HardwareSensorData:
        """
        Read the latest sensor values from the IMU and camera.

        Returns a zero-valued :class:`HardwareSensorData` until real
        hardware drivers are integrated.
        """
        # TODO: integrate with IMU and camera drivers
        import time

        return HardwareSensorData(timestamp=time.time())

    def write_display(self, text: str, line: int = 0) -> None:
        """
        Write *text* to the specified *line* of the HUD display.

        Parameters
        ----------
        text : str
            The text to render.
        line : int
            Display line index (0 = top).
        """
        # TODO: integrate with HUD display driver
        pass

    def set_led(self, pattern_code: int) -> None:
        """
        Set the helmet status LEDs to the given *pattern_code*.

        Pattern codes are defined in :mod:`embedded.led_controller.LEDPattern`.
        """
        # TODO: write to GPIO pins via MCU
        pass

    def shutdown(self) -> None:
        """
        Gracefully power down all hardware peripherals.
        Call before the application exits.
        """
        # TODO: implement safe shutdown sequence
        pass

    def get_battery_level(self) -> int:
        """Return the current battery charge as a percentage (0–100)."""
        # TODO: read from power management IC
        return 100
