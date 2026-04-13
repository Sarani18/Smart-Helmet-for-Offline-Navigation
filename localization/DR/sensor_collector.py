"""
Sensor Collector
----------------
Abstraction layer representing Android's SensorManager API.

In the real deployment, this module's methods are called by the
Android Foreground Service which registers listeners on:
    - SensorManager.registerListener(TYPE_ACCELEROMETER, SENSOR_DELAY_GAME)
    - SensorManager.registerListener(TYPE_GYROSCOPE, SENSOR_DELAY_GAME)
    - SensorManager.registerListener(TYPE_MAGNETIC_FIELD, SENSOR_DELAY_UI)
    - SensorManager.registerListener(TYPE_ROTATION_VECTOR, SENSOR_DELAY_GAME)
    - SensorManager.registerListener(TYPE_STEP_COUNTER, SENSOR_DELAY_NORMAL)
    - LocationManager.requestLocationUpdates(GPS_PROVIDER, 1000, 1)

For testing and demo, we simulate these readings with the RideSimulator.

Architecture (in production on the phone):
┌────────────────────────────────────────────────┐
│  Android Foreground Service (runs background)  │
│                                                │
│  SensorEventListener.onSensorChanged(event) ──►│
│  LocationListener.onLocationChanged(loc)   ──► │
│                                                │
│  SensorCollector.on_sensor_event(type, values) │
│         │                                      │
│         ▼                                      │
│  DeadReckoningEngine.process_reading()         │
│         │                                      │
│         ▼                                      │
│  Predicted Position → Navigation Module        │
└────────────────────────────────────────────────┘
"""

from __future__ import annotations

import time
import math
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from enum import Enum

logger = logging.getLogger("sensor_collector")


class AndroidSensorType(Enum):
    """
    Maps directly to Android SensorManager constants.

    In Java this would be:
        Sensor.TYPE_ACCELEROMETER  = 1
        Sensor.TYPE_GYROSCOPE      = 4
        Sensor.TYPE_MAGNETIC_FIELD = 2
        Sensor.TYPE_ROTATION_VECTOR = 11
        Sensor.TYPE_STEP_COUNTER    = 19
        Sensor.TYPE_LINEAR_ACCELERATION = 10
    """
    TYPE_ACCELEROMETER = 1
    TYPE_GYROSCOPE = 4
    TYPE_MAGNETIC_FIELD = 2
    TYPE_LINEAR_ACCELERATION = 10
    TYPE_ROTATION_VECTOR = 11
    TYPE_STEP_COUNTER = 19


class SensorDelay(Enum):
    """Android SensorManager delay constants (microseconds)."""
    SENSOR_DELAY_FASTEST = 0        # ~0 ms
    SENSOR_DELAY_GAME = 20_000      # 20 ms (50 Hz)
    SENSOR_DELAY_UI = 66_667        # 66 ms (15 Hz)
    SENSOR_DELAY_NORMAL = 200_000   # 200 ms (5 Hz)


@dataclass
class SensorEvent:
    """
    Mirrors Android's SensorEvent class.

    In the Android app, this is created from:
        public void onSensorChanged(SensorEvent event) {
            float[] values = event.values;
            long timestamp = event.timestamp;  // nanoseconds since boot
            int accuracy = event.accuracy;
        }
    """
    sensor_type: AndroidSensorType
    values: List[float]
    timestamp_ns: int      # nanoseconds (boot-time clock)
    accuracy: int = 3      # 0=unreliable, 1=low, 2=medium, 3=high


@dataclass
class LocationFix:
    """
    Mirrors Android's Location class from LocationManager.

    In the Android app:
        LocationListener.onLocationChanged(Location location) {
            double lat = location.getLatitude();
            double lon = location.getLongitude();
            float speed = location.getSpeed();       // m/s
            float bearing = location.getBearing();    // degrees 0-360
            float accuracy = location.getAccuracy();  // metres
        }
    """
    latitude: float
    longitude: float
    speed_mps: float = 0.0
    bearing_deg: float = 0.0
    accuracy_m: float = 10.0
    timestamp_ms: int = 0
    has_speed: bool = True
    has_bearing: bool = True
    provider: str = "gps"


class SensorCollector:
    """
    Abstraction of Android's SensorManager + LocationManager.

    In production, the Android Foreground Service fills this with real data:

    ```java
    // Android Java code (what runs on the phone)
    public class SensorForegroundService extends Service
            implements SensorEventListener, LocationListener {

        private SensorManager sensorManager;
        private LocationManager locationManager;
        private DeadReckoningBridge drBridge;  // calls Python DR via JNI/HTTP

        @Override
        public void onCreate() {
            sensorManager = (SensorManager) getSystemService(SENSOR_SERVICE);
            locationManager = (LocationManager) getSystemService(LOCATION_SERVICE);

            // Register sensor listeners
            sensorManager.registerListener(this,
                sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER),
                SensorManager.SENSOR_DELAY_GAME);
            sensorManager.registerListener(this,
                sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE),
                SensorManager.SENSOR_DELAY_GAME);
            sensorManager.registerListener(this,
                sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR),
                SensorManager.SENSOR_DELAY_GAME);

            // Register GPS
            locationManager.requestLocationUpdates(
                LocationManager.GPS_PROVIDER, 1000, 1, this);
        }

        @Override
        public void onSensorChanged(SensorEvent event) {
            drBridge.feedSensorEvent(event);
        }

        @Override
        public void onLocationChanged(Location location) {
            drBridge.feedGPSFix(location);
        }
    }
    ```

    For Python testing, we use RideSimulator to generate these events.
    """

    def __init__(self) -> None:
        self._listeners: Dict[AndroidSensorType, List[Callable]] = {}
        self._gps_listeners: List[Callable] = []
        self._gps_available: bool = True
        self._last_gps_fix: Optional[LocationFix] = None
        self._registered_sensors: Dict[AndroidSensorType, SensorDelay] = {}

    # ------------------------------------------------------------------
    # Sensor registration (mirrors SensorManager.registerListener)
    # ------------------------------------------------------------------
    def register_listener(
        self,
        sensor_type: AndroidSensorType,
        callback: Callable[[SensorEvent], None],
        delay: SensorDelay = SensorDelay.SENSOR_DELAY_GAME,
    ) -> None:
        """
        Register a callback for a sensor type.
        Mirrors: sensorManager.registerListener(listener, sensor, delay)
        """
        if sensor_type not in self._listeners:
            self._listeners[sensor_type] = []
        self._listeners[sensor_type].append(callback)
        self._registered_sensors[sensor_type] = delay
        logger.info(
            f"Registered listener for {sensor_type.name} "
            f"(delay={delay.value}μs)"
        )

    def register_gps_listener(
        self,
        callback: Callable[[LocationFix], None],
    ) -> None:
        """
        Register a GPS location callback.
        Mirrors: locationManager.requestLocationUpdates(GPS_PROVIDER, ...)
        """
        self._gps_listeners.append(callback)
        logger.info("Registered GPS listener")

    def unregister_all(self) -> None:
        """Mirrors: sensorManager.unregisterListener(this)"""
        self._listeners.clear()
        self._gps_listeners.clear()
        self._registered_sensors.clear()

    # ------------------------------------------------------------------
    # Event dispatch (called by Android service or simulator)
    # ------------------------------------------------------------------
    def dispatch_sensor_event(self, event: SensorEvent) -> None:
        """
        Feed a sensor event into the collector.
        In production, called from onSensorChanged().
        In testing, called from RideSimulator.
        """
        callbacks = self._listeners.get(event.sensor_type, [])
        for cb in callbacks:
            cb(event)

    def dispatch_gps_fix(self, fix: LocationFix) -> None:
        """
        Feed a GPS location fix.
        In production, called from onLocationChanged().
        """
        self._last_gps_fix = fix
        for cb in self._gps_listeners:
            cb(fix)

    def set_gps_available(self, available: bool) -> None:
        """Simulate GPS signal loss/recovery."""
        self._gps_available = available
        if available:
            logger.info("GPS signal RESTORED")
        else:
            logger.warning("GPS signal LOST — switching to dead reckoning")

    @property
    def gps_available(self) -> bool:
        return self._gps_available

    @property
    def last_gps_fix(self) -> Optional[LocationFix]:
        return self._last_gps_fix
