/**
 * Smart Helmet — TypeScript type definitions
 *
 * Ported from Python source-of-truth files:
 *   - navigation/contracts.py       (enums, event/nav messages)
 *   - embedded/nav_interface.py     (UIStateMessage, UIActionMessage)
 *   - embedded/bluetooth_comm.py    (ConnectionState)
 *   - embedded/led_controller.py    (LEDPattern)
 *   - embedded/instruction_parser.py (InstructionCode)
 *   - embedded/app_interface/ui_manager.py (NavDisplay)
 *   - communication/protocol.py     (PacketType, BLEPacket)
 *   - localization/sensor_fusion.py (IMUReading, Orientation)
 *   - localization/dead_reckoning.py (Position, MotionSample)
 *   - navigation/route_processor.py (Waypoint, RouteStep, Route)
 *   - localization/map_matching.py   (RoadSegment)
 *
 * Keep enum string values in sync with Python enum values exactly.
 * Do NOT add enums or interfaces not present in Python — they diverge.
 */

// ─────────────────────────────────────────────────────────────────────────────
// ENUMS — navigation/contracts.py
// ─────────────────────────────────────────────────────────────────────────────

export enum LocalizationEventType {
  TURN     = 'TURN',
  LANDMARK = 'LANDMARK',
  SIGNBOARD = 'SIGNBOARD',
}

export enum TurnClass {
  SLIGHT_LEFT  = 'SLIGHT_LEFT',
  LEFT         = 'LEFT',
  SLIGHT_RIGHT = 'SLIGHT_RIGHT',
  RIGHT        = 'RIGHT',
  U_TURN       = 'U_TURN',
  STRAIGHT     = 'STRAIGHT',
}

export enum LandmarkClass {
  TRAFFIC_LIGHT = 'TRAFFIC_LIGHT',
  BRIDGE        = 'BRIDGE',
  FUEL_STATION  = 'FUEL_STATION',
  JUNCTION      = 'JUNCTION',
  ROUNDABOUT    = 'ROUNDABOUT',
}

export enum NavMode {
  ONLINE   = 'ONLINE',
  OFFLINE  = 'OFFLINE',
  DEGRADED = 'DEGRADED',
}

export enum PositionMode {
  GPS     = 'GPS',
  VISUAL  = 'VISUAL',
  UNKNOWN = 'UNKNOWN',
}

export enum NetworkStatus {
  ONLINE  = 'ONLINE',
  OFFLINE = 'OFFLINE',
}

export enum LocalizationModuleType {
  VISUAL        = 'VISUAL',
  DEAD_RECKONING = 'DEAD_RECKONING',
}

export enum LocalizationControlAction {
  START = 'START',
  STOP  = 'STOP',
}

export enum UIActionType {
  START_NAVIGATION = 'START_NAVIGATION',
  STOP_NAVIGATION  = 'STOP_NAVIGATION',
  REROUTE_REQUEST  = 'REROUTE_REQUEST',
}

// ─────────────────────────────────────────────────────────────────────────────
// ENUMS — embedded modules
// ─────────────────────────────────────────────────────────────────────────────

// embedded/bluetooth_comm.py — ConnectionState
export enum ConnectionState {
  DISCONNECTED = 'DISCONNECTED',
  SCANNING     = 'SCANNING',
  CONNECTING   = 'CONNECTING',
  CONNECTED    = 'CONNECTED',
  ERROR        = 'ERROR',
}

// embedded/led_controller.py — LEDPattern
export enum LEDPattern {
  OFF        = 'OFF',
  SOLID_GREEN = 'SOLID_GREEN',
  BLINK_LEFT  = 'BLINK_LEFT',
  BLINK_RIGHT = 'BLINK_RIGHT',
  BLINK_BOTH  = 'BLINK_BOTH',
  SOLID_RED   = 'SOLID_RED',
  RAPID_RED   = 'RAPID_RED',
  SOLID_BLUE  = 'SOLID_BLUE',
  BLINK_BLUE  = 'BLINK_BLUE',
}

// embedded/instruction_parser.py — InstructionCode (5-byte instruction packet)
export enum InstructionCode {
  NOP           = 0x00,
  TURN_LEFT     = 0x01,
  TURN_RIGHT    = 0x02,
  GO_STRAIGHT   = 0x03,
  U_TURN        = 0x04,
  ARRIVE        = 0x05,
  GPS_LOST      = 0x10,
  GPS_RESTORED  = 0x11,
  CRASH_ALERT   = 0x20,
  SOS_TRIGGERED = 0x21,
  LED_OFF       = 0xFF,
}

// communication/protocol.py — PacketType (8-byte BLE packet)
export enum PacketType {
  NAV_INSTRUCTION = 0x01,
  GPS_STATUS      = 0x02,
  SPEED_UPDATE    = 0x03,
  IMU_DATA        = 0x10,
  BATTERY_LEVEL   = 0x11,
  ACK             = 0x12,
  CRASH_EVENT     = 0x20,
  SOS_CONFIRM     = 0x21,
  HEARTBEAT       = 0xFE,
  RESET           = 0xFF,
}

// ─────────────────────────────────────────────────────────────────────────────
// CONSTANTS
// ─────────────────────────────────────────────────────────────────────────────

// communication/protocol.py
export const BLE_MAGIC_BYTE = 0xAB;
export const BLE_PACKET_SIZE = 8;

// embedded/instruction_parser.py
export const INSTRUCTION_PACKET_SIZE = 5;

// communication/sync_manager.py
export const HEARTBEAT_INTERVAL_MS = 2000;
export const HEARTBEAT_TIMEOUT_MS  = 6000;

// localization/sensor_fusion.py
export const CRASH_PITCH_THRESHOLD_DEG = 60;
export const CRASH_ROLL_THRESHOLD_DEG  = 75;
export const SENSOR_FUSION_ALPHA       = 0.98;

// localization/dead_reckoning.py
export const DEAD_RECKONING_DRIFT_RATE = 0.02; // 2% of distance travelled

// localization/map_matching.py
export const MAP_MATCH_MAX_DISTANCE_M = 50;

// navigation/confidence_tracker.py
export const CONFIDENCE_INITIAL          = 0.7;
export const CONFIDENCE_DEGRADED_THRESHOLD = 0.45;
export const CONFIDENCE_DECAY_INTERVAL_MS  = 5000;
export const CONFIDENCE_DECAY_PER_INTERVAL = 0.03;

// navigation/api_service.py
export const DEGRADED_NO_EVENT_MS    = 15000;
export const OFFLINE_AFTER_FAILURES  = 2; // 2-tap hysteresis
export const ONLINE_AFTER_SUCCESSES  = 2; // 2-tap hysteresis

// navigation/route_processor.py
export const ROUTE_CORRIDOR_M = 500;

// embedded/app_interface/ui_manager.py — RSSI → signal bars thresholds (dBm)
export const RSSI_4_BARS = -60;
export const RSSI_3_BARS = -70;
export const RSSI_2_BARS = -80;
export const RSSI_1_BAR  = -90;

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — PRIMARY UI CONTRACT
// Source: navigation/contracts.py + embedded/nav_interface.py
// ─────────────────────────────────────────────────────────────────────────────

export interface UIStateMessage {
  session_id: string;
  ts_ms: number;
  nav_mode: NavMode;
  position_mode: PositionMode;
  next_instruction_text: string;
  distance_to_next_m: number;
  confidence: number;            // [0.0, 1.0]
  off_route_flag: boolean;
  destination_reached_flag: boolean;
  active_step_index: number;
  route_polyline: [number, number][]; // [[lat, lon], ...]
  degraded?: boolean;
  degraded_reason?: string;
}

export interface StartNavigationPayload {
  origin: string;
  destination: string;
}

export interface RerouteRequestPayload {
  reason: string;
}

export interface UIActionMessage {
  session_id: string;
  ts_ms: number;
  action_type: UIActionType;
  payload: StartNavigationPayload | RerouteRequestPayload | Record<string, never>;
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — LOCALIZATION EVENTS
// Source: navigation/contracts.py
// ─────────────────────────────────────────────────────────────────────────────

export interface TurnPayload {
  turn_class: TurnClass;
}

export interface LandmarkPayload {
  landmark_class: LandmarkClass;
  map_hint_name?: string;
}

export interface SignboardPayload {
  text: string;
  direction_hint?: TurnClass;
}

export interface EventMessage {
  session_id: string;
  event_id: string;
  ts_ms: number;
  event_type: LocalizationEventType;
  confidence: number;
  payload: TurnPayload | LandmarkPayload | SignboardPayload;
  heading_deg?: number;
  speed_mps?: number;
}

export interface NavHintMessage {
  session_id: string;
  ts_ms: number;
  expected_next_turn: TurnClass;
  distance_to_next_turn_m: number;
}

export interface ConnectivityStatusMessage {
  ts_ms: number;
  network_available: boolean;
  internet_reachable: boolean;
}

export interface LocalizationControlMessage {
  session_id: string;
  ts_ms: number;
  module: LocalizationModuleType;
  action: LocalizationControlAction;
  reason: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — SENSOR / LOCALIZATION
// Source: localization/sensor_fusion.py, dead_reckoning.py, heading_tracker.py
// ─────────────────────────────────────────────────────────────────────────────

export interface IMUReading {
  accel_x: number;  // m/s²
  accel_y: number;
  accel_z: number;
  gyro_x: number;   // degrees/second
  gyro_y: number;
  gyro_z: number;
  timestamp: number; // Unix seconds
}

export interface Orientation {
  roll: number;  // degrees — rotation around forward axis
  pitch: number; // degrees — rotation around side axis
  yaw: number;   // degrees — rotation around vertical axis (heading)
}

export interface Position {
  latitude: number;
  longitude: number;
  uncertainty_meters: number;
}

export interface MotionSample {
  speed_mps: number;
  heading_degrees: number; // 0–360°, clockwise from North
  timestamp: number;       // Unix seconds
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — ROUTE
// Source: navigation/route_processor.py
// ─────────────────────────────────────────────────────────────────────────────

export interface Waypoint {
  latitude: number;
  longitude: number;
  label: string;
}

export interface RouteStep {
  instruction: string;
  distance_meters: number;
  waypoint: Waypoint;
}

export interface Route {
  origin: Waypoint;
  destination: Waypoint;
  steps: RouteStep[];
  total_distance_meters: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — BLE / COMMUNICATION
// Source: communication/protocol.py, embedded modules
// ─────────────────────────────────────────────────────────────────────────────

export interface BLEPacket {
  packet_type: PacketType;
  sequence_number: number; // 0–65535 rolling
  payload: Uint8Array;     // 3 bytes, zero-padded
}

export interface ParsedInstruction {
  code: InstructionCode;
  distance_meters: number;
  text: string;
}

export interface HelmetDevice {
  address: string; // BLE MAC address or UUID (platform-dependent)
  name: string;
  rssi: number;    // dBm
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — UI STATE (embedded app_interface)
// Source: embedded/app_interface/ui_manager.py
// ─────────────────────────────────────────────────────────────────────────────

export interface NavDisplay {
  instruction: string;
  distance_meters: number;
  speed_kph: number;
  gps_active: boolean;
  heading_degrees: number;
  signal_strength: number; // 0–4 bars (converted from RSSI dBm)
}

// ─────────────────────────────────────────────────────────────────────────────
// INTERFACES — MAP
// Source: localization/map_matching.py, navigation/map_manager.py
// ─────────────────────────────────────────────────────────────────────────────

export interface RoadSegment {
  id: string;
  name: string;
  start: { lat: number; lon: number };
  end:   { lat: number; lon: number };
}
