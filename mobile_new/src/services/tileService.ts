/**
 * OSM tile cache for react-native-maps UrlTile.
 *
 * Key design: react-native-maps MapTileProvider.java (the native Android code behind UrlTile)
 * saves tiles as {tileCachePath}/{zoom}/{x}/{y}  — NO file extension.
 * It also reads from that same path before fetching the network.
 *
 * So we point UrlTile.tileCachePath at TILE_CACHE_DIR and the native layer handles
 * both online fetching AND offline serving — no RNFS download needed for basic use.
 *
 * downloadTilesForRoute / downloadTilesAroundPoint use the same path convention so that
 * pre-fetched tiles are found by the native cache read.
 */
import RNFS from 'react-native-fs';
import type { LatLon } from './routeService';

/** Plain filesystem path — no file:// prefix. Used both here and by UrlTile.tileCachePath. */
export const TILE_CACHE_DIR = `${RNFS.DocumentDirectoryPath}/osm_tile_cache`;

const OSM_TILE_URL = 'https://tile.openstreetmap.org';
const MAX_CACHE_BYTES = 200 * 1024 * 1024; // 200 MB
const DEFAULT_ZOOM_LEVELS = [14, 15];

export interface TileDownloadProgress {
  downloaded: number;
  total: number;
  failed: number;
}

type ProgressCallback = (p: TileDownloadProgress) => void;

/**
 * Download tiles in a square area around a single point (e.g. current GPS location).
 * Saves in the same format as MapTileProvider.java: {TILE_CACHE_DIR}/{z}/{x}/{y} (no extension)
 * so that UrlTile's native cache read finds them when offline.
 * radiusKm controls how far out to cache (2km covers a useful area at z14).
 */
export async function downloadTilesAroundPoint(
  center: LatLon,
  radiusKm: number = 2,
  zoomLevels: number[] = DEFAULT_ZOOM_LEVELS,
  onProgress?: ProgressCallback,
): Promise<TileDownloadProgress> {
  // Approximate lat/lon degrees from km
  const latDelta = radiusKm / 111.0;
  const lonDelta = radiusKm / (111.0 * Math.cos((center.lat * Math.PI) / 180));
  const bbox: BBox = {
    minLat: center.lat - latDelta,
    maxLat: center.lat + latDelta,
    minLon: center.lon - lonDelta,
    maxLon: center.lon + lonDelta,
  };
  await ensureDir(TILE_CACHE_DIR);
  const tileList = enumerateTiles(bbox, zoomLevels);
  const progress: TileDownloadProgress = { downloaded: 0, total: tileList.length, failed: 0 };
  const BATCH = 10;
  for (let i = 0; i < tileList.length; i += BATCH) {
    const batch = tileList.slice(i, i + BATCH);
    await Promise.all(
      batch.map(async ({ z, x, y }) => {
        try {
          await downloadTile(z, x, y);
          progress.downloaded++;
        } catch (_) {
          progress.failed++;
        }
        onProgress?.(progress);
      }),
    );
  }
  return progress;
}

/**
 * Download all tiles covering the route polyline bounding box.
 * Skips tiles already cached on disk.
 */
export async function downloadTilesForRoute(
  polyline: LatLon[],
  zoomLevels: number[] = DEFAULT_ZOOM_LEVELS,
  onProgress?: ProgressCallback,
): Promise<TileDownloadProgress> {
  await ensureDir(TILE_CACHE_DIR);

  const bbox = computeBBox(polyline);
  const tileList = enumerateTiles(bbox, zoomLevels);

  const progress: TileDownloadProgress = {
    downloaded: 0,
    total: tileList.length,
    failed: 0,
  };

  // Download in batches of 10 to avoid overwhelming the network
  const BATCH = 10;
  for (let i = 0; i < tileList.length; i += BATCH) {
    const batch = tileList.slice(i, i + BATCH);
    await Promise.all(
      batch.map(async ({ z, x, y }) => {
        try {
          await downloadTile(z, x, y);
          progress.downloaded++;
        } catch (_) {
          progress.failed++;
        }
        onProgress?.(progress);
      }),
    );
  }

  await trimCache();
  return progress;
}

// ---- Internal helpers ----

interface BBox {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
}

interface TileCoord {
  z: number;
  x: number;
  y: number;
}

function computeBBox(polyline: LatLon[]): BBox {
  const lats = polyline.map(p => p.lat);
  const lons = polyline.map(p => p.lon);
  return {
    minLat: Math.min(...lats),
    maxLat: Math.max(...lats),
    minLon: Math.min(...lons),
    maxLon: Math.max(...lons),
  };
}

function latLonToTile(lat: number, lon: number, zoom: number): TileCoord {
  const n = Math.pow(2, zoom);
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
    n,
  );
  return { z: zoom, x, y };
}

function enumerateTiles(bbox: BBox, zoomLevels: number[]): TileCoord[] {
  const tiles: TileCoord[] = [];
  for (const z of zoomLevels) {
    const topLeft = latLonToTile(bbox.maxLat, bbox.minLon, z);
    const bottomRight = latLonToTile(bbox.minLat, bbox.maxLon, z);
    for (let x = topLeft.x; x <= bottomRight.x; x++) {
      for (let y = topLeft.y; y <= bottomRight.y; y++) {
        tiles.push({ z, x, y });
      }
    }
  }
  return tiles;
}

async function downloadTile(z: number, x: number, y: number): Promise<void> {
  const dir = `${TILE_CACHE_DIR}/${z}/${x}`;
  // No .png extension — matches MapTileProvider.java getTileFilename() format:
  //   return tileCachePath + '/' + zoom + "/" + x + "/" + y;
  const path = `${dir}/${y}`;

  const exists = await RNFS.exists(path);
  if (exists) {
    return;
  }

  await ensureDir(dir);
  const url = `${OSM_TILE_URL}/${z}/${x}/${y}.png`;
  await RNFS.downloadFile({
    fromUrl: url,
    toFile: path,
    headers: { 'User-Agent': 'SmartHelmetNav/1.0' },
    connectionTimeout: 10000,
    readTimeout: 10000,
  }).promise;
}

async function ensureDir(path: string): Promise<void> {
  const exists = await RNFS.exists(path);
  if (!exists) {
    await RNFS.mkdir(path);
  }
}

async function trimCache(): Promise<void> {
  try {
    const items = await RNFS.readDir(TILE_CACHE_DIR);
    // Get all png files recursively (simplified: scan z-level dirs)
    const files: { path: string; mtime: Date; size: number }[] = [];
    for (const item of items) {
      if (item.isDirectory()) {
        const zItems = await RNFS.readDir(item.path);
        for (const xi of zItems) {
          if (xi.isDirectory()) {
            const yItems = await RNFS.readDir(xi.path);
            for (const yi of yItems) {
              files.push({
                path: yi.path,
                mtime: new Date(yi.mtime ?? 0),
                size: parseInt(String(yi.size ?? '0'), 10),
              });
            }
          }
        }
      }
    }

    const totalBytes = files.reduce((s, f) => s + f.size, 0);
    if (totalBytes <= MAX_CACHE_BYTES) {
      return;
    }

    // Evict oldest files first
    files.sort((a, b) => a.mtime.getTime() - b.mtime.getTime());
    let bytesRemoved = 0;
    const toRemove = totalBytes - MAX_CACHE_BYTES;
    for (const f of files) {
      if (bytesRemoved >= toRemove) {
        break;
      }
      await RNFS.unlink(f.path);
      bytesRemoved += f.size;
    }
  } catch (e) {
    console.warn('Tile cache trim failed:', e);
  }
}
