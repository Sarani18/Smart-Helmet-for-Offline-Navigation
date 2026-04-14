/**
 * HelmetImageService  —  WiFi image pull from the Smart Helmet camera
 *
 * Transport: HTTP over the helmet's WiFi hotspot.
 *
 * Flow per frame:
 *   1. Phone connects to helmet hotspot (192.168.4.1, ESP32 default).
 *   2. Phone calls GET /frame — the helmet captures one frame and streams
 *      back the JPEG bytes in the HTTP response body.
 *   3. HelmetImageService converts the response to a base64 data-URI and
 *      passes it to the caller (vision module).
 *
 * Hardware notes:
 *   - Default IP 192.168.4.1 is the ESP32 SoftAP address.
 *     For Raspberry Pi or a custom network, set HELMET_HOTSPOT_BASE_URL
 *     via the exported constant override.
 *   - The helmet's HTTP server must implement GET /frame (returns JPEG).
 *   - No BLE involvement for image transfer — BLE handles control only.
 *
 * This service is intentionally stateless. The caller (vision module /
 * NavigationScreen) decides when to request frames and at what rate.
 */

// Default helmet hotspot address — override if using Raspberry Pi or custom net
export let HELMET_IMAGE_URL = 'http://192.168.4.1/frame';

export interface HelmetFrame {
  /** JPEG image as base64 data-URI: "data:image/jpeg;base64,..." */
  dataUri:      string;
  /** Unix ms when the frame was received */
  receivedAtMs: number;
  /** HTTP content-type returned by the helmet */
  contentType:  string;
}

/**
 * Pull one frame from the helmet camera.
 *
 * @param timeoutMs - Request timeout in ms (default 3 s — camera capture takes ~200 ms)
 * @returns HelmetFrame on success, null if the request fails or times out.
 */
export async function requestFrame(timeoutMs = 3000): Promise<HelmetFrame | null> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const response = await fetch(HELMET_IMAGE_URL, {
      method: 'GET',
      signal: controller.signal,
    });

    clearTimeout(timer);

    if (!response.ok) {return null;}

    const contentType = response.headers.get('content-type') ?? 'image/jpeg';
    const arrayBuffer = await response.arrayBuffer();
    const base64      = Buffer.from(arrayBuffer).toString('base64');
    const dataUri     = `data:${contentType};base64,${base64}`;

    return {dataUri, receivedAtMs: Date.now(), contentType};
  } catch {
    return null;
  }
}

/**
 * Check whether the helmet's HTTP server is reachable (quick ping).
 * Returns true if GET /frame responds within 1 s (any HTTP status).
 */
export async function isHelmetReachable(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 1000);
    await fetch(HELMET_IMAGE_URL, {method: 'HEAD', signal: controller.signal});
    clearTimeout(timer);
    return true;
  } catch {
    return false;
  }
}
