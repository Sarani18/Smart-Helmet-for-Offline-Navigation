# Application Entry Point

## Purpose

`app/main.py` contains `SmartHelmetApp` — the top-level class that wires every
module together and drives the main application loop.

---

## Lifecycle

```
SmartHelmetApp.initialize()
    └── HardwareInterface.initialize()
    └── SyncManager.register_gps_change_callback(...)
    └── SyncManager.register_link_unhealthy_callback(...)

SmartHelmetApp.start_navigation(route_data)
    └── RouteProcessor.load_route(route_data)
    └── OfflineCache.save_route("active_route", route_data)
    └── _send_nav_instruction(first_step)

SmartHelmetApp.run()  ←── loops forever calling tick() every 0.1 s
    └── tick()
        ├── HardwareInterface.read_sensors()
        ├── SensorFusion.update(imu_reading)
        ├── HeadingTracker.update(yaw)
        ├── SensorFusion.is_crash_detected() → crash alert if True
        ├── DeadReckoning.update(sample)   (when GPS is lost)
        ├── MapMatcher.match(position)
        ├── RouteProcessor.revalidate_route(lat, lon)
        └── SyncManager.tick()

SmartHelmetApp.shutdown()
    └── BluetoothComm.disconnect()
    └── HardwareInterface.shutdown()
```

---

## Running

```bash
cd Smart-Helmet-for-Offline-Navigation
python -m app.main
```

Or import and drive it programmatically:

```python
from app.main import SmartHelmetApp

app = SmartHelmetApp()
app.initialize()
app.start_navigation(my_route_data)
app.tick()   # or app.run() for a blocking loop
app.shutdown()
```
