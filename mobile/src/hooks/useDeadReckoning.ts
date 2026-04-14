/**
 * useDeadReckoning
 *
 * Ports three Python modules to TypeScript, bound to Android sensor APIs:
 *
 *   localization/sensor_fusion.py
 *     Complementary filter (α=0.98) — fuses accelerometer tilt with gyro
 *     integration to produce stable roll/pitch/yaw.
 *
 *   localization/heading_tracker.py
 *     Circular mean over a sliding window of 10, spike rejection >90°.
 *
 *   localization/dead_reckoning.py
 *     Haversine displacement: dist=speed×dt, delta_lat/lon from heading.
 *     Uncertainty grows at 2% of distance travelled (DEAD_RECKONING_DRIFT_RATE).
 *
 * Activation:
 *   - Starts listening to sensors immediately but only posts DR events to NCS
 *     when `drActive` prop is true (set by useGPS when NCS sends DEAD_RECKONING
 *     START command after 2-tap hysteresis triggers OFFLINE mode).
 *
 * Anchor:
 *   - Call anchor(lat, lon) on each fresh GPS fix to reset the DR origin.
 *     This is wired up via the onGPSFix callback in useGPS.
 *
 * Sensor notes (react-native-sensors):
 *   - Gyroscope values are in rad/s → converted to deg/s here (× 180/π).
 *   - Timestamps are in milliseconds → converted to seconds (÷ 1000).
 *   - Update interval set to 50 ms (20 Hz) to satisfy <50 ms latency requirement.
 */

import {useCallback, useEffect, useRef, useState} from 'react';
import {
  accelerometer,
  gyroscope,
  setUpdateIntervalForType,
  SensorTypes,
} from 'react-native-sensors';
import {postDeadReckoningEvent} from '../services/NCSService';
import {Position} from '../types';

// ── Constants (mirror Python constants exactly) ───────────────────────────────

const SENSOR_FUSION_ALPHA    = 0.98;      // complementary filter weight
const DEAD_RECKONING_DRIFT   = 0.02;      // 2% of distance → uncertainty growth
const HEADING_WINDOW         = 10;        // circular mean window size
const HEADING_SPIKE_THRESHOLD = 90;       // degrees — reject if jump > this
const SENSOR_INTERVAL_MS     = 50;        // 20 Hz — <50 ms latency requirement
const RAD_TO_DEG             = 180 / Math.PI;
const DEG_TO_RAD             = Math.PI / 180;

// ── Types ─────────────────────────────────────────────────────────────────────

export interface DRState {
  position:        Position | null;  // current dead-reckoned position
  heading:         number;           // smoothed heading, degrees clockwise from N
  roll:            number;           // degrees
  pitch:           number;           // degrees
  isActive:        boolean;          // true when drActive prop is true
  hasAnchor:       boolean;          // true after first GPS anchor
}

export interface DRCallbacks {
  /** Called on each DR position update (for map marker) */
  onPosition?: (position: Position, heading: number) => void;
}

// ── Hook ─────────────────────────────────────────────────────────────────────

let drEventCounter = 0;

export function useDeadReckoning(
  sessionId: string,
  drActive: boolean,
  callbacks: DRCallbacks = {},
) {
  const [state, setState] = useState<DRState>({
    position:  null,
    heading:   0,
    roll:      0,
    pitch:     0,
    isActive:  false,
    hasAnchor: false,
  });

  // ── Mutable algorithm state (refs avoid stale closure captures) ───────────

  // Sensor fusion state
  const rollRef       = useRef(0);
  const pitchRef      = useRef(0);
  const yawRef        = useRef(0);
  const prevGyroTsRef = useRef<number | null>(null);  // seconds

  // Heading tracker circular window
  const headingWindowRef = useRef<number[]>([]);

  // Dead reckoning state
  const anchorRef      = useRef<{lat: number; lon: number} | null>(null);
  const positionRef    = useRef<Position | null>(null);
  const uncertaintyRef = useRef(0);

  // Current speed from GPS (m/s) — updated via anchor/GPS fix
  const speedRef       = useRef(0);
  const prevDRTsRef    = useRef<number | null>(null);  // seconds

  // Stable callback ref
  const callbacksRef   = useRef(callbacks);
  useEffect(() => { callbacksRef.current = callbacks; }, [callbacks]);

  // drActive ref for use inside sensor callbacks
  const drActiveRef = useRef(drActive);
  useEffect(() => { drActiveRef.current = drActive; }, [drActive]);

  const sessionRef = useRef(sessionId);
  useEffect(() => { sessionRef.current = sessionId; }, [sessionId]);

  // ── Sensor fusion helpers ─────────────────────────────────────────────────

  /**
   * Complementary filter step — mirrors sensor_fusion.py update().
   *
   * roll  = α×(roll + gyro_x×dt) + (1−α)×accel_roll
   * pitch = α×(pitch + gyro_y×dt) + (1−α)×accel_pitch
   * yaw   = (yaw + gyro_z×dt) % 360  [accel cannot correct yaw]
   */
  const fusionUpdate = useCallback((
    accelX: number, accelY: number, accelZ: number,
    gyroXDeg: number, gyroYDeg: number, gyroZDeg: number,
    dt: number,
  ) => {
    // Tilt from accelerometer (gravity vector)
    const accelRoll  = Math.atan2(accelY, accelZ) * RAD_TO_DEG;
    const accelPitch = Math.atan2(-accelX, Math.sqrt(accelY * accelY + accelZ * accelZ)) * RAD_TO_DEG;

    rollRef.current  = SENSOR_FUSION_ALPHA * (rollRef.current  + gyroXDeg * dt)
                     + (1 - SENSOR_FUSION_ALPHA) * accelRoll;
    pitchRef.current = SENSOR_FUSION_ALPHA * (pitchRef.current + gyroYDeg * dt)
                     + (1 - SENSOR_FUSION_ALPHA) * accelPitch;
    yawRef.current   = ((yawRef.current + gyroZDeg * dt) % 360 + 360) % 360;
  }, []);

  // ── Heading tracker helpers ───────────────────────────────────────────────

  /**
   * Circular mean of angles in degrees — mirrors heading_tracker.py.
   * Handles wrap-around correctly (e.g. mean of 350° and 10° = 0°).
   */
  const circularMean = useCallback((angles: number[]): number => {
    if (angles.length === 0) {return 0;}
    const sinSum = angles.reduce((s, a) => s + Math.sin(a * DEG_TO_RAD), 0);
    const cosSum = angles.reduce((s, a) => s + Math.cos(a * DEG_TO_RAD), 0);
    const mean = Math.atan2(sinSum, cosSum) * RAD_TO_DEG;
    return (mean + 360) % 360;
  }, []);

  /**
   * Update the heading window with a new raw yaw reading.
   * Rejects spikes (angular distance > HEADING_SPIKE_THRESHOLD from current mean).
   * Returns the smoothed heading.
   */
  const updateHeading = useCallback((rawYaw: number): number => {
    const window = headingWindowRef.current;

    if (window.length > 0) {
      const current = circularMean(window);
      // Angular distance (0–180)
      let diff = Math.abs(rawYaw - current);
      if (diff > 180) {diff = 360 - diff;}
      if (diff > HEADING_SPIKE_THRESHOLD) {
        return current; // reject spike — return last good mean
      }
    }

    window.push(rawYaw);
    if (window.length > HEADING_WINDOW) {
      window.shift();
    }
    return circularMean(window);
  }, [circularMean]);

  // ── Dead reckoning step ───────────────────────────────────────────────────

  /**
   * Haversine displacement step — mirrors dead_reckoning.py update().
   *
   * dist        = speed × dt
   * delta_lat   = (dist × cos(heading_rad)) / 111320
   * delta_lon   = (dist × sin(heading_rad)) / (111320 × cos(lat_rad))
   * uncertainty += dist × DEAD_RECKONING_DRIFT
   */
  const drStep = useCallback((heading: number, nowSec: number) => {
    const anchor = anchorRef.current;
    if (!anchor) {return;}

    const prev = prevDRTsRef.current;
    prevDRTsRef.current = nowSec;
    if (prev === null) {return;}

    const dt     = nowSec - prev;
    if (dt <= 0 || dt > 2) {return;} // ignore stale gaps

    const speed   = speedRef.current;
    const dist    = speed * dt;

    const hdgRad  = heading * DEG_TO_RAD;
    const latRad  = (positionRef.current?.latitude ?? anchor.lat) * DEG_TO_RAD;

    const currentLat = positionRef.current?.latitude  ?? anchor.lat;
    const currentLon = positionRef.current?.longitude ?? anchor.lon;

    const deltaLat = (dist * Math.cos(hdgRad)) / 111320;
    const deltaLon = (dist * Math.sin(hdgRad)) / (111320 * Math.cos(latRad));

    uncertaintyRef.current += dist * DEAD_RECKONING_DRIFT;

    const newPos: Position = {
      latitude:           currentLat + deltaLat,
      longitude:          currentLon + deltaLon,
      uncertainty_meters: uncertaintyRef.current,
    };

    positionRef.current = newPos;
    return newPos;
  }, []);

  // ── NCS DR event publisher ────────────────────────────────────────────────

  const publishDREvent = useCallback(async (
    position: Position,
    heading: number,
  ) => {
    if (!drActiveRef.current) {return;}
    const confidence = Math.max(0, Math.min(1,
      1 - Math.min(position.uncertainty_meters, 100) / 100,
    ));
    const eventId = `dr_${sessionRef.current}_${++drEventCounter}`;
    try {
      await postDeadReckoningEvent(
        sessionRef.current,
        eventId,
        position.latitude,
        position.longitude,
        position.uncertainty_meters,
        heading,
        speedRef.current,
        confidence,
      );
    } catch {
      // Best-effort — NCS DR endpoint is "future" per INTEGRATION_CONSIDERATIONS.md
    }
  }, []);

  // ── Gyroscope subscription ────────────────────────────────────────────────

  useEffect(() => {
    setUpdateIntervalForType(SensorTypes.gyroscope, SENSOR_INTERVAL_MS);

    // Accelerometer readings cached for fusion (gyro callback reads them)
    const accelCache = {x: 0, y: 0, z: 1}; // default: upright (z=gravity)

    const accelSub = accelerometer.subscribe(({x, y, z}) => {
      accelCache.x = x;
      accelCache.y = y;
      accelCache.z = z;
    });

    const gyroSub = gyroscope.subscribe(({x, y, z, timestamp}) => {
      // timestamp from react-native-sensors is in milliseconds → convert to seconds
      const nowSec = timestamp / 1000;

      // Gyro is in rad/s → convert to deg/s for the Python-ported algorithm
      const gyroXDeg = x * RAD_TO_DEG;
      const gyroYDeg = y * RAD_TO_DEG;
      const gyroZDeg = z * RAD_TO_DEG;

      let dt = 0;
      if (prevGyroTsRef.current !== null) {
        dt = nowSec - prevGyroTsRef.current;
      }
      prevGyroTsRef.current = nowSec;

      if (dt <= 0 || dt > 0.5) {return;} // skip first sample or large gaps

      // ── Sensor fusion step ──────────────────────────────────────────────
      fusionUpdate(
        accelCache.x, accelCache.y, accelCache.z,
        gyroXDeg, gyroYDeg, gyroZDeg,
        dt,
      );

      const smoothedHeading = updateHeading(yawRef.current);

      // ── Dead reckoning step (only when we have an anchor) ───────────────
      const newPos = drStep(smoothedHeading, nowSec);

      // ── Publish state updates ───────────────────────────────────────────
      setState(s => ({
        ...s,
        roll:     rollRef.current,
        pitch:    pitchRef.current,
        heading:  smoothedHeading,
        position: positionRef.current,
        isActive: drActiveRef.current,
      }));

      if (newPos) {
        callbacksRef.current.onPosition?.(newPos, smoothedHeading);
        publishDREvent(newPos, smoothedHeading);
      }
    });

    return () => {
      accelSub.unsubscribe();
      gyroSub.unsubscribe();
    };
  }, [fusionUpdate, updateHeading, drStep, publishDREvent]);

  // ── Public anchor method ──────────────────────────────────────────────────

  /**
   * Call this on each fresh GPS fix to reset the DR origin.
   * Wired from useGPS `onGPSFix` callback in the parent component.
   */
  const anchor = useCallback((lat: number, lon: number, speed: number = 0) => {
    anchorRef.current      = {lat, lon};
    uncertaintyRef.current = 0;
    speedRef.current       = speed;
    prevDRTsRef.current    = null; // force dt reset on next gyro tick

    const anchored: Position = {latitude: lat, longitude: lon, uncertainty_meters: 0};
    positionRef.current = anchored;

    setState(s => ({...s, position: anchored, hasAnchor: true}));
  }, []);

  /**
   * Update current speed estimate (call whenever GPS provides a fresh fix).
   */
  const updateSpeed = useCallback((speedMps: number) => {
    speedRef.current = speedMps;
  }, []);

  return {state, anchor, updateSpeed};
}
