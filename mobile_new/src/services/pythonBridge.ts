/**
 * Thin TypeScript wrapper over the SmartHelmetPython Kotlin Native Module.
 *
 * All methods are synchronous (isBlockingSynchronousMethod on the Kotlin side)
 * so they can be called inline from sensorService listeners and the position
 * coordinator without awaiting Promises.
 *
 * Falls back to throwing a clear error when running on a platform where the
 * native module is not available (iOS, Jest, web) so callers can detect it.
 */
import {NativeModules} from 'react-native';

interface SmartHelmetPythonNativeModule {
  anchorDr(lat: number, lon: number): null;
  updateDr(speedMps: number, headingDeg: number, timestampS: number): string;
  getDrPosition(): string;
  isDrAnchored(): boolean;
  resetDr(): null;
  updateHeading(
    ax: number, ay: number, az: number,
    gx: number, gy: number, gz: number,
    timestampS: number,
  ): number;
  getHeading(): number;
  isHeadingInitialized(): boolean;
  isCrashDetected(): boolean;
  resetHeading(): null;
}

const native: SmartHelmetPythonNativeModule | undefined =
  NativeModules.SmartHelmetPython;

function assertAvailable(): void {
  if (!native) {
    throw new Error(
      'SmartHelmetPython native module not found. ' +
      'Ensure Chaquopy is configured and the app was built with gradle.',
    );
  }
}

export interface DRPosition {
  lat: number;
  lon: number;
  uncertainty_m: number;
}

export const pythonBridge = {
  isAvailable(): boolean {
    return native != null;
  },

  // ── Dead Reckoning ───────────────────────────────────────────────────────

  anchorDr(lat: number, lon: number): void {
    assertAvailable();
    native!.anchorDr(lat, lon);
  },

  updateDr(speedMps: number, headingDeg: number, ts_ms: number): DRPosition | null {
    assertAvailable();
    const json = native!.updateDr(speedMps, headingDeg, ts_ms / 1000);
    if (json === 'null') {
      return null;
    }
    return JSON.parse(json) as DRPosition;
  },

  getDrPosition(): DRPosition | null {
    assertAvailable();
    const json = native!.getDrPosition();
    if (json === 'null') {
      return null;
    }
    return JSON.parse(json) as DRPosition;
  },

  isDrAnchored(): boolean {
    assertAvailable();
    return native!.isDrAnchored();
  },

  resetDr(): void {
    assertAvailable();
    native!.resetDr();
  },

  // ── Heading / Sensor Fusion ─────────────────────────────────────────────

  updateHeading(
    ax: number, ay: number, az: number,
    gx: number, gy: number, gz: number,
    ts_ms: number,
  ): number {
    assertAvailable();
    return native!.updateHeading(ax, ay, az, gx, gy, gz, ts_ms / 1000);
  },

  getHeading(): number {
    assertAvailable();
    return native!.getHeading();
  },

  isHeadingInitialized(): boolean {
    assertAvailable();
    return native!.isHeadingInitialized();
  },

  isCrashDetected(): boolean {
    assertAvailable();
    return native!.isCrashDetected();
  },

  resetHeading(): void {
    assertAvailable();
    native!.resetHeading();
  },
};
