/**
 * BLE service for communicating with the Smart Helmet.
 * Uses react-native-ble-plx 3.2.0 inside react-native-background-actions.
 *
 * 8-byte packet format (from communication/protocol.py):
 *   [0] magic = 0xAB
 *   [1] type code
 *   [2-3] sequence number (big-endian)
 *   [4-6] payload (3 bytes)
 *   [7] XOR checksum (bytes 0–6)
 *
 * Graceful: if helmet not found or BLE unavailable, navigation continues unaffected.
 */
import {BleManager, Device, State as BLEState} from 'react-native-ble-plx';
import {Platform} from 'react-native';

// Packet type codes (from communication/protocol.py)
const PKT_NAV_INSTRUCTION = 0x01;
const PKT_GPS_STATUS = 0x02;
const PKT_HEARTBEAT = 0xfe;
const MAGIC = 0xab;

// Target device names
const HELMET_NAMES = ['SmartHelmet_BLE', 'NaviHelmet'];

// The BleManager is a singleton — instantiated outside component lifecycle
const bleManager = new BleManager();

let connectedDevice: Device | null = null;
let seqNum = 0;
let scanActive = false;
let bleReady = false;

// Characteristic UUIDs — update to match actual helmet firmware
const SERVICE_UUID = '0000ffe0-0000-1000-8000-00805f9b34fb';
const CHAR_UUID = '0000ffe1-0000-1000-8000-00805f9b34fb';

/** Start scanning and connecting to the helmet. Non-blocking. */
export async function startBLE(): Promise<void> {
  if (Platform.OS !== 'android') {
    return;
  }
  try {
    const state = await bleManager.state();
    if (state !== BLEState.PoweredOn) {
      console.warn('BLE not powered on — helmet connection skipped.');
      return;
    }
    bleReady = true;
    startScan();
  } catch (e) {
    console.warn('BLE init failed (no crash):', e);
  }
}

export function stopBLE(): void {
  try {
    if (scanActive) {
      bleManager.stopDeviceScan();
      scanActive = false;
    }
    connectedDevice?.cancelConnection();
    connectedDevice = null;
    bleReady = false;
  } catch (e) {
    console.warn('BLE stop error:', e);
  }
}

export function isBLEConnected(): boolean {
  return connectedDevice !== null;
}

/**
 * Send a navigation instruction to the helmet.
 * @param instructionText  Human-readable instruction (used for GPS_STATUS byte)
 * @param distanceM        Distance to next manoeuvre in metres
 */
export function sendNavInstruction(
  _instructionText: string,
  distanceM: number,
): void {
  if (!connectedDevice || !bleReady) {
    return;
  }
  try {
    const distClamped = Math.min(distanceM, 0xffff);
    const payload = [
      (distClamped >> 8) & 0xff,
      distClamped & 0xff,
      0x00, // reserved
    ];
    const packet = buildPacket(PKT_NAV_INSTRUCTION, payload);
    writePacket(packet);
  } catch (e) {
    console.warn('BLE send error:', e);
  }
}

/** Notify helmet of GPS availability. */
export function sendGPSStatus(available: boolean): void {
  if (!connectedDevice || !bleReady) {
    return;
  }
  try {
    const packet = buildPacket(PKT_GPS_STATUS, [available ? 0x01 : 0x00, 0, 0]);
    writePacket(packet);
  } catch (e) {
    console.warn('BLE GPS status error:', e);
  }
}

// ---- Internal helpers ----

function startScan(): void {
  if (scanActive) {
    return;
  }
  scanActive = true;

  bleManager.startDeviceScan(null, null, async (error, device) => {
    if (error) {
      console.warn('BLE scan error:', error.message);
      scanActive = false;
      return;
    }
    if (device && device.name && HELMET_NAMES.includes(device.name)) {
      bleManager.stopDeviceScan();
      scanActive = false;
      await connectToDevice(device);
    }
  });
}

async function connectToDevice(device: Device): Promise<void> {
  try {
    const connected = await device.connect();
    await connected.discoverAllServicesAndCharacteristics();
    connectedDevice = connected;
    console.log('Smart Helmet connected:', device.name);

    // Listen for disconnection and attempt reconnect
    bleManager.onDeviceDisconnected(device.id, () => {
      console.warn('Helmet disconnected — will retry...');
      connectedDevice = null;
      setTimeout(() => startScan(), 5000);
    });
  } catch (e) {
    console.warn('Helmet connection failed (navigation continues):', e);
    connectedDevice = null;
  }
}

function buildPacket(typeCode: number, payload: number[]): Uint8Array {
  seqNum = (seqNum + 1) & 0xffff;
  const buf = new Uint8Array(8);
  buf[0] = MAGIC;
  buf[1] = typeCode;
  buf[2] = (seqNum >> 8) & 0xff;
  buf[3] = seqNum & 0xff;
  buf[4] = payload[0] ?? 0;
  buf[5] = payload[1] ?? 0;
  buf[6] = payload[2] ?? 0;
  // XOR checksum over bytes 0–6
  buf[7] = buf[0] ^ buf[1] ^ buf[2] ^ buf[3] ^ buf[4] ^ buf[5] ^ buf[6];
  return buf;
}

function writePacket(packet: Uint8Array): void {
  if (!connectedDevice) {
    return;
  }
  // Convert Uint8Array to base64 for react-native-ble-plx
  const base64 = Buffer.from(packet).toString('base64');
  connectedDevice
    .writeCharacteristicWithoutResponseForService(SERVICE_UUID, CHAR_UUID, base64)
    .catch(e => console.warn('BLE write failed:', e));
}
