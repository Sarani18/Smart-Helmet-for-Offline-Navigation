/**
 * Wi-Fi HTTP service for the ESP32 LED controller.
 *
 * The ESP32 joins the phone hotspot below and also exposes its own fallback AP.
 * Android will not join Wi-Fi networks from JS alone, so connection attempts
 * here mean "ping the ESP32 API on the currently reachable network".
 */

export const HELMET_DEVICE_NAME = 'SmartHelmet-ESP32';
export const PHONE_HOTSPOT_SSID = 'Vijit hotspot';
export const PHONE_HOTSPOT_PASSWORD = 'buvijit1418bu';
export const HELMET_AP_SSID = 'SmartHelmet-ESP32-AP';
export const HELMET_AP_PASSWORD = 'helmet1234';
export const HELMET_AP_IP = '192.168.4.1';
export const HELMET_PHONE_HOTSPOT_IP = '192.168.43.42';

const DEFAULT_BASE_URL = `http://${HELMET_PHONE_HOTSPOT_IP}`;
const CANDIDATE_BASE_URLS = [
  `http://${HELMET_PHONE_HOTSPOT_IP}`,
  `http://${HELMET_AP_IP}`,
  `http://${HELMET_DEVICE_NAME}.local`,
];
const REQUEST_TIMEOUT_MS = 1200;
const DUPLICATE_RETRY_MS = 3000;
const TURN_NOW_DISTANCE_M = 40;

export type HelmetCommand =
  | 'CLEAR'
  | 'LEFT_PREPARE'
  | 'LEFT_NOW'
  | 'RIGHT_PREPARE'
  | 'RIGHT_NOW'
  | 'HAZARD'
  | 'ARRIVED';

interface NavigationCueInput {
  instructionText: string;
  distanceToNextM: number;
  offRoute: boolean;
  destinationReached: boolean;
}

export interface HelmetConnectionResult {
  connected: boolean;
  baseUrl: string;
  mode?: string;
  status?: string;
}

let lastCommand: HelmetCommand | null = null;
let lastAttemptMs = 0;
let activeBaseUrl = DEFAULT_BASE_URL;

export function setHelmetHost(hostOrUrl: string): void {
  const trimmed = hostOrUrl.trim();
  if (trimmed.length === 0) {
    return;
  }
  activeBaseUrl = trimmed.startsWith('http://') || trimmed.startsWith('https://')
    ? trimmed.replace(/\/+$/, '')
    : `http://${trimmed.replace(/\/+$/, '')}`;
  resetHelmetCommandCache();
}

export function resetHelmetCommandCache(): void {
  lastCommand = null;
  lastAttemptMs = 0;
}

export function commandForNavigationCue(
  cue: NavigationCueInput,
): HelmetCommand {
  if (cue.destinationReached || includesAny(cue.instructionText, ['arrived'])) {
    return 'ARRIVED';
  }
  if (cue.offRoute) {
    return 'HAZARD';
  }

  const isLeft = includesAny(cue.instructionText, ['left', 'u-turn']);
  const isRight = includesAny(cue.instructionText, ['right']);

  if (isLeft) {
    return cue.distanceToNextM >= TURN_NOW_DISTANCE_M
      ? 'LEFT_PREPARE'
      : 'LEFT_NOW';
  }
  if (isRight) {
    return cue.distanceToNextM >= TURN_NOW_DISTANCE_M
      ? 'RIGHT_PREPARE'
      : 'RIGHT_NOW';
  }

  return 'CLEAR';
}

export async function sendNavigationCue(
  cue: NavigationCueInput,
): Promise<void> {
  await sendCommand(commandForNavigationCue(cue));
}

export async function clearHelmet(): Promise<void> {
  await sendCommand('CLEAR');
}

export async function sendCommand(command: HelmetCommand): Promise<void> {
  const nowMs = Date.now();
  if (command === lastCommand && nowMs - lastAttemptMs < DUPLICATE_RETRY_MS) {
    return;
  }

  lastCommand = command;
  lastAttemptMs = nowMs;

  try {
    await fetchWithTimeout(
      `${activeBaseUrl}/command?cmd=${encodeURIComponent(command)}`,
    );
  } catch (e) {
    console.warn(`Helmet Wi-Fi command failed (${command}):`, e);
  }
}

export async function checkHelmetConnection(): Promise<HelmetConnectionResult> {
  const candidates = [
    activeBaseUrl,
    ...CANDIDATE_BASE_URLS.filter(url => url !== activeBaseUrl),
  ];

  for (const baseUrl of candidates) {
    try {
      const health = await fetchJson(`${baseUrl}/health`);
      if (health && health.ok === true) {
        activeBaseUrl = baseUrl;
        const status = await fetchJson(`${baseUrl}/status`).catch(() => null);
        return {
          connected: true,
          baseUrl,
          mode: typeof status?.wifi_mode === 'string' ? status.wifi_mode : undefined,
          status: typeof status?.status === 'string' ? status.status : undefined,
        };
      }
    } catch (_e) {
      // Try the next known endpoint.
    }
  }

  return {
    connected: false,
    baseUrl: activeBaseUrl,
  };
}

function includesAny(text: string, needles: string[]): boolean {
  const lower = text.toLowerCase();
  return needles.some(needle => lower.includes(needle));
}

async function fetchWithTimeout(url: string): Promise<void> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {method: 'GET', signal: controller.signal});
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } finally {
    clearTimeout(timer);
  }
}

async function fetchJson(url: string): Promise<any> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(url, {method: 'GET', signal: controller.signal});
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
  } finally {
    clearTimeout(timer);
  }
}
