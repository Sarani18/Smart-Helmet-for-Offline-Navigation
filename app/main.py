"""
Smart Helmet Application – Main Entry Point
-------------------------------------------
Composes all software modules and runs the application main loop.
"""

from __future__ import annotations

import time
from typing import Optional

from navigation import RouteProcessor, OfflineCache
from localization import SensorFusion, DeadReckoning, HeadingTracker, MapMatcher
from localization.sensor_fusion import IMUReading
from localization.dead_reckoning import MotionSample
from embedded import BluetoothComm, LEDController, InstructionParser  # noqa: F401
from embedded.app_interface import UIManager, DeviceManager
from communication import SmartHelmetProtocol, PacketHandler, SyncManager
from communication.protocol import PacketType
from hardware import HardwareInterface


class SmartHelmetApp:
    """
    Top-level application class that wires all modules together.

    Lifecycle
    ---------
    1. ``initialize()``  – set up hardware and establish BLE connection.
    2. ``start_navigation(route_data)`` – load a route and begin guidance.
    3. ``run()``  – main loop; call repeatedly (or from a timer).
    4. ``shutdown()`` – clean up resources.
    """

    LOOP_INTERVAL = 0.1  # seconds per tick

    def __init__(self, hardware: Optional[HardwareInterface] = None) -> None:
        # Hardware
        self._hw = hardware or HardwareInterface()

        # Navigation
        self._route_processor = RouteProcessor()
        self._offline_cache = OfflineCache()

        # Localization
        self._sensor_fusion = SensorFusion()
        self._dead_reckoning = DeadReckoning()
        self._heading_tracker = HeadingTracker()
        self._map_matcher = MapMatcher()

        # Embedded / App Interface
        self._led = LEDController()
        self._parser = InstructionParser()
        self._ui = UIManager()
        self._ble = BluetoothComm()
        self._device_manager = DeviceManager(self._ble)

        # Communication
        self._protocol = SmartHelmetProtocol()
        self._pkt_handler = PacketHandler(self._protocol)
        self._sync = SyncManager(self._pkt_handler, self._protocol)

        # State
        self._gps_active = True
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """Initialize hardware and prepare all modules."""
        ok = self._hw.initialize()
        if not ok:
            return False
        self._sync.register_gps_change_callback(self._on_gps_change)
        self._sync.register_link_unhealthy_callback(self._on_link_unhealthy)
        return True

    def start_navigation(self, route_data: dict) -> bool:
        """
        Load a route and begin navigation guidance.

        Parameters
        ----------
        route_data:
            Raw route dictionary (as returned by a maps API or the offline cache).
        """
        try:
            route = self._route_processor.load_route(route_data)
        except ValueError:
            return False

        # Cache route for offline use
        self._offline_cache.save_route("active_route", route_data)

        # Send first instruction to helmet
        if route.steps:
            first_step = route.steps[0]
            self._send_nav_instruction(first_step.instruction, first_step.distance_meters)
        return True

    def run(self) -> None:
        """
        Start the main event loop.  Runs until :meth:`shutdown` is called.
        For embedding in an async framework, call :meth:`tick` directly.
        """
        self._running = True
        while self._running:
            self.tick()
            time.sleep(self.LOOP_INTERVAL)

    def tick(self) -> None:
        """
        Process one iteration of the main loop:
        1. Read hardware sensors.
        2. Update orientation and heading.
        3. Update dead reckoning if GPS is lost.
        4. Advance route step if needed.
        5. Send heartbeat / sync state.
        """
        # 1. Read sensors
        sensor_data = self._hw.read_sensors()
        imu = IMUReading(
            accel_x=sensor_data.accel_x,
            accel_y=sensor_data.accel_y,
            accel_z=sensor_data.accel_z,
            gyro_x=sensor_data.gyro_x,
            gyro_y=sensor_data.gyro_y,
            gyro_z=sensor_data.gyro_z,
            timestamp=sensor_data.timestamp,
        )

        # 2. Orientation + heading
        orientation = self._sensor_fusion.update(imu)
        heading = self._heading_tracker.update(orientation.yaw)
        self._ui.update_heading(heading)

        # 3. Crash detection
        if self._sensor_fusion.is_crash_detected():
            from embedded.led_controller import LEDPattern
            self._ui.show_crash_alert()
            self._led.apply_pattern(LEDPattern.RAPID_RED)
            pkt = self._protocol.encode(PacketType.CRASH_EVENT, 0)
            self._ble.send(pkt)

        # 4. GPS-denied dead reckoning
        if not self._gps_active:
            sample = MotionSample(
                speed_mps=self._ui.get_display().speed_kph / 3.6,
                heading_degrees=heading,
                timestamp=sensor_data.timestamp,
            )
            position = self._dead_reckoning.update(sample)
            if position:
                snapped, _ = self._map_matcher.match(position)
                effective_pos = snapped or position
                # Revalidate route against estimated position
                self._route_processor.revalidate_route(
                    effective_pos.latitude, effective_pos.longitude
                )

        # 5. Sync tick (heartbeat + retry)
        self._sync.tick()

    def shutdown(self) -> None:
        """Stop the main loop and release all resources."""
        self._running = False
        self._ble.disconnect()
        self._hw.shutdown()

    # ------------------------------------------------------------------
    # Private callbacks
    # ------------------------------------------------------------------

    def _on_gps_change(self, gps_active: bool) -> None:
        self._gps_active = gps_active
        self._ui.update_gps_status(gps_active)
        if not gps_active:
            self._led.apply_pattern(self._led.INSTRUCTION_MAP["gps lost"])

    def _on_link_unhealthy(self) -> None:
        self._device_manager.reconnect()

    def _send_nav_instruction(self, instruction: str, distance_meters: float) -> None:
        self._ui.update_instruction(instruction, distance_meters)
        self._led.instruction_to_led(instruction)
        # Encode and send over BLE
        from embedded.instruction_parser import InstructionCode, ParsedInstruction
        code = InstructionCode.GO_STRAIGHT
        lower = instruction.lower()
        if "left" in lower:
            code = InstructionCode.TURN_LEFT
        elif "right" in lower:
            code = InstructionCode.TURN_RIGHT
        elif "u-turn" in lower:
            code = InstructionCode.U_TURN
        elif "arrive" in lower or "destination" in lower:
            code = InstructionCode.ARRIVE
        parsed = ParsedInstruction(code=code, distance_meters=distance_meters, text=instruction)
        self._ble.send(self._parser.encode(parsed))


if __name__ == "__main__":
    app = SmartHelmetApp()
    if app.initialize():
        app.run()
