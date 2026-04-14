/**
 * useBluetooth  —  Smart Helmet BLE gateway
 *
 * Responsibilities (mirrors embedded/bluetooth_comm.py + communication/protocol.py):
 *
 *  Connection lifecycle
 *    - Scans for devices whose advertised name starts with "SmartHelmet"
 *    - Connects via Nordic UART Service (NUS) — standard ESP32 / RPi BLE UART
 *    - Auto-reconnects up to MAX_RECONNECT_ATTEMPTS on unexpected disconnect
 *    - After exhausted retries → reports BLE_COMPROMISED to NCS and enters ERROR state
 *
 *  Command channel  (phone → helmet, write to NUS TX characteristic)
 *    - sendInstruction(code, distanceM) — NAV_INSTRUCTION packet
 *    - sendGPSStatus(active)            — GPS_STATUS packet
 *    - sendSpeedUpdate(kph)             — SPEED_UPDATE packet
 *    - sendLEDOff()                     — NAV_INSTRUCTION with LED_OFF code
 *
 *  Telemetry channel  (helmet → phone, notify on NUS RX characteristic)
 *    - BATTERY_LEVEL  → updates batteryLevel state
 *    - CRASH_EVENT    → fires onCrashDetected callback
 *    - IMU_DATA       → fires onIMUData callback (for DR / crash detection)
 *    - HEARTBEAT      → resets link-health timer
 *
 *  Heartbeat
 *    - Sends HEARTBEAT every 2 s
 *    - Marks link unhealthy after 6 s without receiving one
 *    - On unhealthy → reports to NCS via sendModuleStatus
 *
 *  Packet format  (bit-exact match to communication/protocol.py)
 *    [0xAB | type | seq_hi | seq_lo | pl0 | pl1 | pl2 | XOR_checksum]
 *
 *  BLE UUIDs  (Nordic UART Service — standard for ESP32 / RPi)
 *    Service:  6E400001-B5A3-F393-E0A9-E50E24DCCA9E
 *    TX char:  6E400002-B5A3-F393-E0A9-E50E24DCCA9E  (phone writes)
 *    RX char:  6E400003-B5A3-F393-E0A9-E50E24DCCA9E  (phone subscribes)
 *    NOTE: hardware team must flash NUS with these UUIDs on the ESP32/RPi.
 */

import {useCallback, useEffect, useRef, useState} from 'react';
import {BleManager, Device, Subscription} from 'react-native-ble-plx';
import {Buffer} from 'buffer';
import {sendModuleStatus} from '../services/NCSService';
import {ConnectionState, PacketType, InstructionCode} from '../types';

// ── BLE UUIDs ─────────────────────────────────────────────────────────────────

const NUS_SERVICE = '6E400001-B5A3-F393-E0A9-E50E24DCCA9E';
const NUS_TX_CHAR = '6E400002-B5A3-F393-E0A9-E50E24DCCA9E'; // phone → helmet (write)
const NUS_RX_CHAR = '6E400003-B5A3-F393-E0A9-E50E24DCCA9E'; // helmet → phone (notify)

// ── Constants ─────────────────────────────────────────────────────────────────

const HELMET_NAME_PREFIX        = 'SmartHelmet';
const HEARTBEAT_INTERVAL_MS     = 2000;
const HEARTBEAT_TIMEOUT_MS      = 6000;
const MAX_RECONNECT_ATTEMPTS    = 3;
const RECONNECT_DELAY_MS        = 1500;
const BLE_MAGIC                 = 0xAB;

// ── Singleton BleManager (one instance per app process) ──────────────────────
// Creating multiple BleManager instances causes native layer conflicts.
let _manager: BleManager | null = null;
function getManager(): BleManager {
  if (!_manager) {_manager = new BleManager();}
  return _manager;
}

// ── Packet codec  (mirrors communication/protocol.py exactly) ─────────────────

function encodePacket(type: PacketType, seq: number, payload: number[] = []): string {
  const buf = new Uint8Array(8);
  buf[0] = BLE_MAGIC;
  buf[1] = type as number;
  buf[2] = (seq >> 8) & 0xFF;
  buf[3] = seq & 0xFF;
  buf[4] = payload[0] ?? 0;
  buf[5] = payload[1] ?? 0;
  buf[6] = payload[2] ?? 0;
  let xor = 0;
  for (let i = 0; i < 7; i++) {xor ^= buf[i];}
  buf[7] = xor;
  return Buffer.from(buf).toString('base64');
}

interface DecodedPacket {
  type:    PacketType;
  seq:     number;
  payload: Uint8Array;
}

function decodePacket(base64: string): DecodedPacket | null {
  try {
    const buf = Buffer.from(base64, 'base64');
    if (buf.length !== 8 || buf[0] !== BLE_MAGIC) {return null;}
    let xor = 0;
    for (let i = 0; i < 7; i++) {xor ^= buf[i];}
    if (buf[7] !== xor) {return null;}
    return {
      type:    buf[1] as PacketType,
      seq:     (buf[2] << 8) | buf[3],
      payload: new Uint8Array([buf[4], buf[5], buf[6]]),
    };
  } catch {
    return null;
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BLEState {
  connectionState: ConnectionState;
  deviceName:      string | null;
  batteryLevel:    number | null;  // 0–100 %
  linkHealthy:     boolean;
  lastError:       string | null;
}

export interface BLECallbacks {
  onCrashDetected?: () => void;
  onIMUData?:       (ax: number, ay: number, az: number) => void;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

export function useBluetooth(sessionId: string, callbacks: BLECallbacks = {}) {
  const [state, setState] = useState<BLEState>({
    connectionState: ConnectionState.DISCONNECTED,
    deviceName:      null,
    batteryLevel:    null,
    linkHealthy:     true,
    lastError:       null,
  });

  const deviceRef           = useRef<Device | null>(null);
  const rxSubRef            = useRef<Subscription | null>(null);
  const heartbeatTimerRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatRxRef      = useRef<number>(Date.now());
  const seqRef              = useRef(0);
  const reconnectCountRef   = useRef(0);
  const sessionRef          = useRef(sessionId);
  const callbacksRef        = useRef(callbacks);
  const intendedDisconnect  = useRef(false);

  useEffect(() => { sessionRef.current   = sessionId; },  [sessionId]);
  useEffect(() => { callbacksRef.current = callbacks; }, [callbacks]);

  // ── Sequence counter ──────────────────────────────────────────────────────

  const nextSeq = useCallback(() => {
    seqRef.current = (seqRef.current + 1) & 0xFFFF;
    return seqRef.current;
  }, []);

  // ── Write a packet to the helmet ──────────────────────────────────────────

  const writePacket = useCallback(async (type: PacketType, payload: number[] = []) => {
    const device = deviceRef.current;
    if (!device) {return;}
    try {
      const encoded = encodePacket(type, nextSeq(), payload);
      await device.writeCharacteristicWithResponseForService(
        NUS_SERVICE, NUS_TX_CHAR, encoded,
      );
    } catch {
      // best-effort send — transient BLE write errors are tolerated
    }
  }, [nextSeq]);

  // ── Incoming packet handler ───────────────────────────────────────────────

  const handleRxPacket = useCallback((base64: string) => {
    const pkt = decodePacket(base64);
    if (!pkt) {return;}

    switch (pkt.type) {
      case PacketType.HEARTBEAT:
        heartbeatRxRef.current = Date.now();
        setState(s => s.linkHealthy ? s : {...s, linkHealthy: true});
        break;

      case PacketType.BATTERY_LEVEL:
        setState(s => ({...s, batteryLevel: pkt.payload[0]}));
        break;

      case PacketType.CRASH_EVENT:
        callbacksRef.current.onCrashDetected?.();
        break;

      case PacketType.IMU_DATA: {
        // Payload packs two 12-bit signed values per byte pair.
        // Encoding: [ax_hi | ax_lo | ay_hi] — simple 8-bit scaled values
        // (exact encoding defined by ESP32 firmware; parse as signed int8 here)
        const ax = (pkt.payload[0] << 24 >> 24);
        const ay = (pkt.payload[1] << 24 >> 24);
        const az = (pkt.payload[2] << 24 >> 24);
        callbacksRef.current.onIMUData?.(ax, ay, az);
        break;
      }

      case PacketType.ACK:
        // Acknowledged — no action needed at this layer
        break;

      default:
        break;
    }
  }, []);

  // ── Heartbeat loop ────────────────────────────────────────────────────────

  const startHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {return;}
    heartbeatRxRef.current = Date.now();

    heartbeatTimerRef.current = setInterval(async () => {
      await writePacket(PacketType.HEARTBEAT);

      const msSinceRx = Date.now() - heartbeatRxRef.current;
      if (msSinceRx > HEARTBEAT_TIMEOUT_MS) {
        setState(s => s.linkHealthy ? {...s, linkHealthy: false} : s);
        // Report to NCS best-effort
        if (sessionRef.current) {
          sendModuleStatus(sessionRef.current, 'BLE', 'compromised', 'heartbeat_timeout')
            .catch(() => {});
        }
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [writePacket]);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  // ── Subscribe to notifications (helmet → phone) ───────────────────────────

  const subscribeRX = useCallback((device: Device) => {
    rxSubRef.current?.remove();
    rxSubRef.current = device.monitorCharacteristicForService(
      NUS_SERVICE, NUS_RX_CHAR,
      (error, char) => {
        if (error || !char?.value) {return;}
        handleRxPacket(char.value);
      },
    );
  }, [handleRxPacket]);

  // ── Connect to a specific device ──────────────────────────────────────────

  const connectToDevice = useCallback(async (device: Device) => {
    try {
      setState(s => ({...s, connectionState: ConnectionState.CONNECTING, lastError: null}));
      const connected = await device.connect();
      await connected.discoverAllServicesAndCharacteristics();

      deviceRef.current = connected;
      reconnectCountRef.current = 0;

      setState(s => ({
        ...s,
        connectionState: ConnectionState.CONNECTED,
        deviceName:      device.name ?? 'SmartHelmet',
      }));

      subscribeRX(connected);
      startHeartbeat();

      // Watch for unexpected disconnect
      connected.onDisconnected((error) => {
        rxSubRef.current?.remove();
        rxSubRef.current = null;
        stopHeartbeat();
        deviceRef.current = null;

        if (intendedDisconnect.current) {
          intendedDisconnect.current = false;
          setState(s => ({...s, connectionState: ConnectionState.DISCONNECTED}));
          return;
        }

        setState(s => ({...s, connectionState: ConnectionState.DISCONNECTED,
          lastError: error?.message ?? 'Disconnected unexpectedly'}));

        // Auto-reconnect
        if (reconnectCountRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectCountRef.current += 1;
          setTimeout(() => connectToDevice(device), RECONNECT_DELAY_MS);
        } else {
          setState(s => ({...s, connectionState: ConnectionState.ERROR,
            lastError: 'Max reconnect attempts reached'}));
          if (sessionRef.current) {
            sendModuleStatus(sessionRef.current, 'BLE', 'compromised', 'max_reconnect_exceeded')
              .catch(() => {});
          }
        }
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Connection failed';
      setState(s => ({...s, connectionState: ConnectionState.ERROR, lastError: msg}));
    }
  }, [subscribeRX, startHeartbeat, stopHeartbeat]);

  // ── Public: start scan ────────────────────────────────────────────────────

  const scan = useCallback(() => {
    const manager = getManager();
    setState(s => ({...s, connectionState: ConnectionState.SCANNING}));

    manager.startDeviceScan(null, {allowDuplicates: false}, (error, device) => {
      if (error) {
        setState(s => ({...s,
          connectionState: ConnectionState.ERROR,
          lastError: error.message,
        }));
        return;
      }
      if (device?.name?.startsWith(HELMET_NAME_PREFIX)) {
        manager.stopDeviceScan();
        connectToDevice(device);
      }
    });

    // Auto-stop scan after 15 s if nothing found
    setTimeout(() => {
      manager.stopDeviceScan();
      setState(s => s.connectionState === ConnectionState.SCANNING
        ? {...s, connectionState: ConnectionState.DISCONNECTED} : s);
    }, 15000);
  }, [connectToDevice]);

  // ── Public: manual disconnect ─────────────────────────────────────────────

  const disconnect = useCallback(async () => {
    intendedDisconnect.current = true;
    stopHeartbeat();
    rxSubRef.current?.remove();
    rxSubRef.current = null;
    if (deviceRef.current) {
      try { await deviceRef.current.cancelConnection(); } catch {}
      deviceRef.current = null;
    }
    setState(s => ({...s, connectionState: ConnectionState.DISCONNECTED}));
  }, [stopHeartbeat]);

  // ── Public: send navigation instruction ──────────────────────────────────

  const sendInstruction = useCallback((code: InstructionCode, distanceMeters: number) => {
    // Instruction 5-byte payload packed into 3 BLE payload bytes:
    //   [code | dist_hi | dist_lo]  (matches instruction_parser.py encode())
    const dist = Math.min(Math.round(distanceMeters), 0xFFFF);
    writePacket(PacketType.NAV_INSTRUCTION, [
      code as number,
      (dist >> 8) & 0xFF,
      dist & 0xFF,
    ]);
  }, [writePacket]);

  // ── Public: send GPS status ───────────────────────────────────────────────

  const sendGPSStatus = useCallback((active: boolean) => {
    // payload[0]: 0x01 = active, 0x00 = lost  (mirrors sync_manager.py notify_gps_change)
    writePacket(PacketType.GPS_STATUS, [active ? 0x01 : 0x00, 0x00, 0x00]);
  }, [writePacket]);

  // ── Public: send speed update ─────────────────────────────────────────────

  const sendSpeedUpdate = useCallback((speedKph: number) => {
    // 0.1 km/h resolution, big-endian (mirrors sync_manager.py update_speed)
    const val = Math.min(Math.round(speedKph * 10), 0xFFFF);
    writePacket(PacketType.SPEED_UPDATE, [(val >> 8) & 0xFF, val & 0xFF, 0x00]);
  }, [writePacket]);

  // ── Public: tell helmet to stop indicating (turn done) ───────────────────

  const sendLEDOff = useCallback(() => {
    writePacket(PacketType.NAV_INSTRUCTION, [InstructionCode.LED_OFF as number, 0x00, 0x00]);
  }, [writePacket]);

  // ── Cleanup on unmount ────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      stopHeartbeat();
      rxSubRef.current?.remove();
      getManager().stopDeviceScan();
    };
  }, [stopHeartbeat]);

  return {state, scan, disconnect, sendInstruction, sendGPSStatus, sendSpeedUpdate, sendLEDOff};
}
