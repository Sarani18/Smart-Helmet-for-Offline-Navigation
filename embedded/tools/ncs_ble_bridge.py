import argparse
import asyncio
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx
from bleak import BleakClient, BleakScanner

from ble_constants import COMMAND_CHAR_UUID, DEFAULT_DEVICE_NAME


@dataclass
class BridgeConfig:
    ncs_base_url: str
    session_id: str
    poll_interval_s: float
    prepare_distance_m: float
    now_distance_m: float
    missed_distance_m: float
    missed_hold_s: float


class CueMapper:
    def __init__(self, cfg: BridgeConfig) -> None:
        self._cfg = cfg
        self._last_step_index: Optional[int] = None
        self._near_turn_since: Optional[float] = None

    def map_ui_state_to_command(self, ui_state: dict) -> str:
        if ui_state.get("destination_reached_flag"):
            self._reset_missed_tracker()
            return "ARRIVED"

        if ui_state.get("off_route_flag"):
            self._reset_missed_tracker()
            return "HAZARD"

        instruction = (ui_state.get("next_instruction_text") or "").lower()
        distance = float(ui_state.get("distance_to_next_m", 0.0))
        step_index = int(ui_state.get("active_step_index", 0))

        direction = self._extract_turn_direction(instruction)
        if direction is None:
            self._reset_missed_tracker()
            return "CLEAR"

        if distance <= self._cfg.missed_distance_m:
            if self._last_step_index == step_index:
                if self._near_turn_since is None:
                    self._near_turn_since = time.time()
                elif (time.time() - self._near_turn_since) >= self._cfg.missed_hold_s:
                    return f"{direction}_MISSED"
            else:
                self._near_turn_since = time.time()
        else:
            self._near_turn_since = None

        self._last_step_index = step_index

        if distance <= self._cfg.now_distance_m:
            return f"{direction}_NOW"
        if distance <= self._cfg.prepare_distance_m:
            return f"{direction}_PREPARE"
        return "CLEAR"

    def _extract_turn_direction(self, instruction: str) -> Optional[str]:
        if "u-turn" in instruction or "u turn" in instruction:
            # Prototype decision: U-turn uses both-side hazard-like cue.
            return None
        if "left" in instruction:
            return "LEFT"
        if "right" in instruction:
            return "RIGHT"
        return None

    def _reset_missed_tracker(self) -> None:
        self._last_step_index = None
        self._near_turn_since = None


async def resolve_address(address: Optional[str], name: str) -> str:
    if address:
        return address

    devices = await BleakScanner.discover(timeout=8.0)
    for device in devices:
        if (device.name or "") == name:
            return device.address

    raise RuntimeError(f"Could not find BLE device named '{name}'.")


async def fetch_ui_state(client: httpx.AsyncClient, cfg: BridgeConfig) -> dict:
    response = await client.post(
        f"{cfg.ncs_base_url.rstrip('/')}/api/navigation/ui/state",
        json={"session_id": cfg.session_id, "ts_ms": int(time.time() * 1000)},
        timeout=5.0,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("accepted", False):
        raise RuntimeError(f"NCS returned non-accepted response: {data}")
    return data["ui_state"]


async def run_bridge(address: str, cfg: BridgeConfig) -> None:
    mapper = CueMapper(cfg)
    last_command = ""

    async with httpx.AsyncClient() as ncs_client, BleakClient(address) as ble_client:
        if not ble_client.is_connected:
            raise RuntimeError("Failed to connect to ESP32 BLE device")

        print("Connected to ESP32. Starting NCS -> BLE relay...")
        print("Press Ctrl+C to stop.")

        while True:
            try:
                ui_state = await fetch_ui_state(ncs_client, cfg)
                command = mapper.map_ui_state_to_command(ui_state)

                if command != last_command:
                    await ble_client.write_gatt_char(
                        COMMAND_CHAR_UUID,
                        command.encode("utf-8"),
                        response=True,
                    )
                    print(
                        f"Sent {command} | instruction='{ui_state.get('next_instruction_text', '')}' "
                        f"distance={ui_state.get('distance_to_next_m', 0)}"
                    )
                    last_command = command
            except Exception as exc:
                print(f"Bridge warning: {exc}")

            await asyncio.sleep(cfg.poll_interval_s)


def parse_args() -> Tuple[argparse.Namespace, BridgeConfig]:
    parser = argparse.ArgumentParser(description="Bridge NCS UI state to ESP32 BLE LED commands")
    parser.add_argument("--session-id", required=True, help="NCS session_id to monitor")
    parser.add_argument("--ncs-base-url", default="http://127.0.0.1:8000", help="NCS base URL")
    parser.add_argument("--address", default=None, help="ESP32 BLE MAC address (optional)")
    parser.add_argument("--name", default=DEFAULT_DEVICE_NAME, help="ESP32 BLE device name")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="Polling interval in seconds")
    parser.add_argument("--prepare-distance", type=float, default=60.0, help="Distance threshold for PREPARE")
    parser.add_argument("--now-distance", type=float, default=20.0, help="Distance threshold for NOW")
    parser.add_argument("--missed-distance", type=float, default=8.0, help="Distance threshold for MISSED check")
    parser.add_argument("--missed-hold", type=float, default=3.0, help="Seconds below missed-distance before MISSED")
    args = parser.parse_args()

    cfg = BridgeConfig(
        ncs_base_url=args.ncs_base_url,
        session_id=args.session_id,
        poll_interval_s=max(0.1, args.poll_interval),
        prepare_distance_m=max(args.now_distance, args.prepare_distance),
        now_distance_m=max(0.0, args.now_distance),
        missed_distance_m=max(0.0, args.missed_distance),
        missed_hold_s=max(0.5, args.missed_hold),
    )
    return args, cfg


async def main() -> None:
    args, cfg = parse_args()
    address = await resolve_address(args.address, args.name)
    await run_bridge(address, cfg)


if __name__ == "__main__":
    asyncio.run(main())
