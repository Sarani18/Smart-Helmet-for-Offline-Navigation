import asyncio
from bleak import BleakScanner


async def main() -> None:
    print("Scanning for BLE devices for 8 seconds...")
    devices = await BleakScanner.discover(timeout=8.0)

    if not devices:
        print("No BLE devices found.")
        return

    print("\nFound devices:")
    for idx, device in enumerate(devices, start=1):
        name = device.name or "<no-name>"
        print(f"{idx}. {name}  [{device.address}]")


if __name__ == "__main__":
    asyncio.run(main())
