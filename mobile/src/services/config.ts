/**
 * NCS connection config.
 *
 * Android emulator → host machine: 10.0.2.2
 * Physical device  → use your laptop's LAN IP (e.g. 192.168.1.42)
 *
 * Run NCS with:
 *   cd <project-root>
 *   pip install fastapi uvicorn httpx
 *   python -m uvicorn navigation.server:app --host 0.0.0.0 --port 8000 --reload
 */
export const NCS_BASE_URL = 'http://10.0.2.2:8000';

/** How often the NavigationScreen polls /api/navigation/ui/state (ms) */
export const NCS_POLL_INTERVAL_MS = 2000;
