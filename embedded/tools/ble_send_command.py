import argparse
import asyncio
from typing import Optional

from bleak import BleakClient, BleakScanner

from ble_constants import (
    COMMAND_CHAR_UUID,
    DEFAULT_DEVICE_NAME,
    STATUS_CHAR_UUID,
    VALID_COMMANDS,
)


def normalize_command(raw: str) -> str:
    value = raw.strip().upper()
    if value not in VALID_COMMANDS:
        allowed = ", ".join(sorted(VALID_COMMANDS))
        raise ValueError(f"Invalid command '{value}'. Allowed: {allowed}")
    return value


async def resolve_address(address: Optional[str], name: str) -> str:
    if address:
        return address

    devices = await BleakScanner.discover(timeout=8.0)
    for device in devices:
        if (device.name or "") == name:
            return device.address

    raise RuntimeError(
        f"Device named '{name}' not found. Run ble_scan.py to verify name/address."
    )


async def write_command(address: str, command: str, wait_ack_s: float) -> None:
    print(f"Connecting to ESP32 at {address}...")
    async with BleakClient(address) as client:
        if not client.is_connected:
            raise RuntimeError("BLE connection failed")

        print(f"Connected. Sending command: {command}")

        ack_event = asyncio.Event()
        ack_text = {"value": ""}

        def on_notify(_: int, data: bytearray) -> None:
            decoded = bytes(data).decode(errors="ignore").strip()
            ack_text["value"] = decoded
            ack_event.set()

        await client.start_notify(STATUS_CHAR_UUID, on_notify)
        await client.write_gatt_char(COMMAND_CHAR_UUID, command.encode("utf-8"), response=True)

        if wait_ack_s > 0:
            try:
                await asyncio.wait_for(ack_event.wait(), timeout=wait_ack_s)
                print(f"ESP32 status: {ack_text['value']}")
            except asyncio.TimeoutError:
                print("No status notify received within timeout (command may still be applied).")

        await client.stop_notify(STATUS_CHAR_UUID)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Send one LED command to ESP32 over BLE")
    parser.add_argument("--command", required=True, help="Cue command")
    parser.add_argument("--address", default=None, help="BLE MAC address (optional)")
    parser.add_argument("--name", default=DEFAULT_DEVICE_NAME, help="BLE device name")
    parser.add_argument("--wait-ack", type=float, default=2.0, help="Seconds to wait for status notify")
    args = parser.parse_args()

    command = normalize_command(args.command)
    address = await resolve_address(args.address, args.name)
    await write_command(address, command, args.wait_ack)


if __name__ == "__main__":
    asyncio.run(main())
