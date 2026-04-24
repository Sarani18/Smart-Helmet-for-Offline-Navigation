/**
 * OSM tile downloader for offline map rendering.
 * Downloads tiles for a route bounding box at zoom levels 14 and 15,
 * saves them to DocumentDirectoryPath/offline_tiles/{z}/{x}/{y}.png.
 * Max cache size ~200MB — evicts oldest tiles when exceeded.
 */
import RNFS from 'react-native-fs';
import type {LatLon} from './routeService';

const TILE_DIR = `${RNFS.DocumentDirectoryPath}/offline_tiles`;
const OSM_TILE_URL = 'https://tile.openstreetmap.org';
const MAX_CACHE_BYTES = 200 * 1024 * 1024; // 200 MB
const DEFAULT_ZOOM_LEVELS = [14, 15];

export interface TileDownloadProgress {
  downloaded: number;
  total: number;
  failed: number;
}

type ProgressCallback = (p: TileDownloadProgress) => void;

/** Returns the local file:// URI for a tile — used by MapView LocalTile. */
export function getTileTemplate(): string {
  return `file://${TILE_DIR}/{z}/{x}/{y}.png`;
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
  await ensureDir(TILE_DIR);

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
      batch.map(async ({z, x, y}) => {
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
  return {z: zoom, x, y};
}

function enumerateTiles(bbox: BBox, zoomLevels: number[]): TileCoord[] {
  const tiles: TileCoord[] = [];
  for (const z of zoomLevels) {
    const topLeft = latLonToTile(bbox.maxLat, bbox.minLon, z);
    const bottomRight = latLonToTile(bbox.minLat, bbox.maxLon, z);
    for (let x = topLeft.x; x <= bottomRight.x; x++) {
      for (let y = topLeft.y; y <= bottomRight.y; y++) {
        tiles.push({z, x, y});
      }
    }
  }
  return tiles;
}

async function downloadTile(z: number, x: number, y: number): Promise<void> {
  const dir = `${TILE_DIR}/${z}/${x}`;
  const path = `${dir}/${y}.png`;

  const exists = await RNFS.exists(path);
  if (exists) {
    return;
  }

  await ensureDir(dir);
  const url = `${OSM_TILE_URL}/${z}/${x}/${y}.png`;
  await RNFS.downloadFile({
    fromUrl: url,
    toFile: path,
    headers: {'User-Agent': 'SmartHelmetNav/1.0'},
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
    const items = await RNFS.readDir(TILE_DIR);
    // Get all png files recursively (simplified: scan z-level dirs)
    const files: {path: string; mtime: Date; size: number}[] = [];
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
