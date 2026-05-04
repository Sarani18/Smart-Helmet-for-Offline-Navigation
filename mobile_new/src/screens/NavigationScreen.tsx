/**
 * NavigationScreen
 *
<<<<<<< HEAD
 * Live navigation using MapLibre GL + OSM tiles — same map stack as the demo
 * and embedded/web_ui.  No Google Maps SDK required.
 *
 * On mount: starts GPS, IMU sensors, DR, BLE, and position coordinator.
 * Position coordinator feeds navigation engine every 500ms and sends map
 * updates (rider position, camera pan) to MapLibreView via postMessage.
=======
 * Standalone live navigation — no NCS server needed.
 * On mount: starts GPS, IMU sensors, DR, BLE, and position coordinator.
 * Position coordinator feeds navigation engine every 500ms.
 * MapView renders offline OSM tiles from DocumentDirectoryPath.
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
 *
 * Sensor failure policy:
 *   GPS lost   → DR mode (DEGRADED badge)
 *   All down   → UNKNOWN badge + warning banner — app stays open, does NOT crash
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  Alert,
<<<<<<< HEAD
=======
  Platform,
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
<<<<<<< HEAD
=======
import MapView, {
  LocalTile,
  Marker,
  Polyline,
  type Region,
} from 'react-native-maps';
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import * as gpsService from '../services/gpsService';
import * as sensorService from '../services/sensorService';
import * as bleService from '../services/bleService';
import * as navigationEngine from '../services/navigationEngine';
import {
  startCoordinator,
  stopCoordinator,
  addPositionListener,
  type CoordinatorPosition,
  type PositionMode,
} from '../services/positionCoordinator';
<<<<<<< HEAD
import {downloadTilesAroundPoint} from '../services/tileService';
import MapLibreView from '../components/MapLibreView';
import type {MapLibreViewRef} from '../components/MapLibreView';
=======
import {getTileTemplate} from '../services/tileService';
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
import type {ParsedRoute, LatLon} from '../services/routeService';

interface Props {
  sessionId: string;
  route: ParsedRoute;
  origin: LatLon;
  dest: LatLon;
  onStop: () => void;
}

type NavMode = 'GPS' | 'DR' | 'UNKNOWN';

interface NavDisplay {
  instruction: string;
  distanceM: number;
<<<<<<< HEAD
  drDistanceTravelledM: number;
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  navMode: NavMode;
  confidence: number;
  offRoute: boolean;
  destinationReached: boolean;
  currentPos: LatLon | null;
<<<<<<< HEAD
=======
  visionActive: boolean;
  landmarkName?: string;
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
}

const INITIAL_NAV: NavDisplay = {
  instruction: 'Acquiring position…',
  distanceM: 0,
<<<<<<< HEAD
  drDistanceTravelledM: 0,
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  navMode: 'UNKNOWN',
  confidence: 0,
  offRoute: false,
  destinationReached: false,
  currentPos: null,
<<<<<<< HEAD
};

const MODE_COLOR: Record<PositionMode, string> = {
  GPS: '#34a853',
  DR: '#fbbc04',
  UNKNOWN: '#ea4335',
};
const MODE_LABEL: Record<PositionMode, string> = {
  GPS: 'GPS',
  DR: 'DEAD RECKONING',
  UNKNOWN: 'NO SIGNAL',
=======
  visionActive: false,
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
};

const NavigationScreen: React.FC<Props> = ({
  sessionId: _sessionId,
  route,
  origin,
  dest,
  onStop,
}) => {
  const insets = useSafeAreaInsets();
<<<<<<< HEAD
  const mapRef = useRef<MapLibreViewRef>(null);
  const [nav, setNav] = useState<NavDisplay>(INITIAL_NAV);
  const [latestIMU, setLatestIMU] = useState<sensorService.IMUReading | null>(null);
  const [sensorStatus, setSensorStatus] = useState(sensorService.getSensorStatus());
  const firstFixDone = useRef(false);
  const arrivedShown = useRef(false);
  const autoFollowMap = useRef(true);

  // Pre-build route coords once ([lon, lat] for MapLibre)
  const routeCoords = useRef<[number, number][]>(
    route.polyline.map(p => [p.lon, p.lat]),
  );

  // ── map ready: draw route + origin/dest pins ────────────────────────────────
  const handleMapReady = useCallback(() => {
    mapRef.current?.send({type: 'setRoute', coords: routeCoords.current});
    mapRef.current?.send({
      type: 'setMarker',
      markerId: 'origin',
      lon: origin.lon,
      lat: origin.lat,
      color: '#34a853',
      markerSize: 16,
    });
    mapRef.current?.send({
      type: 'setMarker',
      markerId: 'dest',
      lon: dest.lon,
      lat: dest.lat,
      color: '#ea4335',
      markerSize: 16,
    });
  }, [origin, dest]);

  // ── position updates from coordinator ──────────────────────────────────────
=======
  const mapRef = useRef<MapView>(null);
  const [nav, setNav] = useState<NavDisplay>(INITIAL_NAV);
  const [mapReady, setMapReady] = useState(false);
  const tileUrl = getTileTemplate();

  const polylineCoords = route.polyline.map(p => ({
    latitude: p.lat,
    longitude: p.lon,
  }));

  // Start all services on mount, tear down on unmount
  useEffect(() => {
    navigationEngine.loadRoute(route);

    gpsService.startGPS();
    sensorService.startSensors();
    startCoordinator();

    // BLE is optional — non-blocking
    bleService.startBLE().catch(e =>
      console.warn('BLE start failed (navigation continues):', e),
    );

    // Listen to coordinator positions
    const unsubscribe = addPositionListener(handlePosition);

    return () => {
      unsubscribe();
      stopCoordinator();
      gpsService.stopGPS();
      sensorService.stopSensors();
      bleService.stopBLE();
      navigationEngine.unloadRoute();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  const handlePosition = useCallback(
    (pos: CoordinatorPosition) => {
      if (pos.lat === 0 && pos.lon === 0 && pos.positionMode === 'UNKNOWN') {
        setNav(prev => ({
          ...prev,
          navMode: 'UNKNOWN',
          confidence: 0,
<<<<<<< HEAD
          drDistanceTravelledM: pos.drDistanceTravelledM,
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
          instruction: 'No sensor data — check GPS and sensors',
        }));
        return;
      }

      const state = navigationEngine.updatePosition(pos.lat, pos.lon);
<<<<<<< HEAD
      const navMode: NavMode =
        pos.positionMode === 'GPS'
          ? 'GPS'
          : pos.positionMode === 'DR'
          ? 'DR'
          : 'UNKNOWN';
=======

      const navMode: NavMode = pos.positionMode === 'GPS'
        ? 'GPS'
        : pos.positionMode === 'DR'
        ? 'DR'
        : 'UNKNOWN';
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

      setNav({
        instruction: state.nextInstructionText,
        distanceM: state.distanceToNextM,
<<<<<<< HEAD
        drDistanceTravelledM: pos.drDistanceTravelledM,
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
        navMode,
        confidence: pos.confidence,
        offRoute: state.offRoute,
        destinationReached: state.destinationReached,
        currentPos: {lat: pos.lat, lon: pos.lon},
<<<<<<< HEAD
      });

      // Update rider dot on map
      mapRef.current?.send({
        type: 'setRider',
        lon: pos.lon,
        lat: pos.lat,
        color: MODE_COLOR[pos.positionMode],
      });

      // Follow until the rider manually pans/zooms, then leave the map under user control.
      if (pos.positionMode !== 'UNKNOWN' && autoFollowMap.current) {
        mapRef.current?.send({
          type: 'flyTo',
          lon: pos.lon,
          lat: pos.lat,
          zoom: 15,
        });
      }

=======
        visionActive: pos.positionMode === 'FUSED',
        landmarkName: pos.landmarkName, 
      });

>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
      // Notify helmet via BLE
      if (bleService.isBLEConnected()) {
        bleService.sendNavInstruction(state.nextInstructionText, state.distanceToNextM);
        bleService.sendGPSStatus(pos.positionMode === 'GPS');
      }

<<<<<<< HEAD
      // On first valid GPS fix, download tiles around current location for offline use
      if (!firstFixDone.current && pos.positionMode === 'GPS') {
        firstFixDone.current = true;
        downloadTilesAroundPoint({lat: pos.lat, lon: pos.lon}, 2, [14, 15]).catch(
          e => console.warn('Tile download around current location failed:', e),
        );
      }

      // Arrived alert — show once
      if (state.destinationReached && !arrivedShown.current) {
        arrivedShown.current = true;
=======
      // Pan map to current position
      if (mapReady && mapRef.current && pos.positionMode !== 'UNKNOWN') {
        mapRef.current.animateToRegion(
          {
            latitude: pos.lat,
            longitude: pos.lon,
            latitudeDelta: 0.005,
            longitudeDelta: 0.005,
          },
          300,
        );
      }

      if (state.destinationReached) {
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
        Alert.alert('Arrived!', 'You have reached your destination.', [
          {text: 'OK', onPress: onStop},
        ]);
      }
    },
<<<<<<< HEAD
    [onStop],
  );

  // ── service lifecycle ───────────────────────────────────────────────────────
  useEffect(() => {
    navigationEngine.loadRoute(route);
    gpsService.startGPS();
    sensorService.startSensors();
    startCoordinator();

    bleService.startBLE().catch(e =>
      console.warn('BLE start failed (navigation continues):', e),
    );

    const unsubscribe = addPositionListener(handlePosition);
    const unsubscribeIMU = sensorService.addIMUListener(setLatestIMU);
    const sensorStatusInterval = setInterval(() => {
      setSensorStatus(sensorService.getSensorStatus());
    }, 500);

    return () => {
      unsubscribe();
      unsubscribeIMU();
      clearInterval(sensorStatusInterval);
      stopCoordinator();
      gpsService.stopGPS();
      sensorService.stopSensors();
      bleService.stopBLE();
      navigationEngine.unloadRoute();
    };
    // handlePosition is stable (useCallback with [onStop])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleRecenter = useCallback(() => {
    if (nav.currentPos) {
      autoFollowMap.current = true;
      mapRef.current?.send({
        type: 'flyTo',
        lon: nav.currentPos.lon,
        lat: nav.currentPos.lat,
        zoom: 15,
      });
    }
  }, [nav.currentPos]);

  const handleMapInteraction = useCallback(() => {
    autoFollowMap.current = false;
  }, []);

  const formatSensor = (value: number): string => value.toFixed(2);
  const formatDistance = (meters: number): string =>
    meters >= 1000 ? `${(meters / 1000).toFixed(2)} km` : `${meters.toFixed(1)} m`;

  return (
    <View style={styles.container}>
      {/* Full-screen MapLibre map — OSM tiles, same as demo and embedded web UI */}
      <MapLibreView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        initialLon={origin.lon}
        initialLat={origin.lat}
        initialZoom={14}
        onReady={handleMapReady}
        onUserInteraction={handleMapInteraction}
      />

      {/* No-signal warning (shown above instruction bar) */}
      {nav.navMode === 'UNKNOWN' && (
        <View style={styles.warningBanner}>
          <Text style={styles.warningText}>
            {sensorService.getSensorError()
              ? `Sensor error: ${sensorService.getSensorError()}`
              : gpsService.getGPSError()
              ? `GPS unavailable: ${gpsService.getGPSError()}`
              : 'No GPS or sensor data — check location permissions and sensors'}
=======
    [mapReady, onStop],
  );

  const initialRegion: Region = {
    latitude: origin.lat,
    longitude: origin.lon,
    latitudeDelta: 0.05,
    longitudeDelta: 0.05,
  };

  const modeColor: Record<PositionMode, string> = {
    GPS: '#34a853',
    DR: '#fbbc04',
    UNKNOWN: '#ea4335',
  };
  const modeLabel: Record<PositionMode, string> = {
    GPS: 'GPS',
    DR: 'DEAD RECKONING',
    UNKNOWN: 'NO SIGNAL',
  };

  return (
    <View style={styles.container}>
      {/* Map */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        mapType={Platform.OS === 'android' ? 'none' : 'standard'}
        provider={undefined}
        rotateEnabled={false}
        initialRegion={initialRegion}
        onMapReady={() => setMapReady(true)}>
        <LocalTile pathTemplate={tileUrl} tileSize={256} zIndex={-1} />

        {/* Route polyline */}
        {polylineCoords.length > 0 && (
          <Polyline
            coordinates={polylineCoords}
            strokeColor="#1a73e8"
            strokeWidth={4}
          />
        )}

        {/* Origin marker */}
        <Marker
          coordinate={{latitude: origin.lat, longitude: origin.lon}}
          title="Start"
          pinColor="green"
        />

        {/* Destination marker */}
        <Marker
          coordinate={{latitude: dest.lat, longitude: dest.lon}}
          title="Destination"
          pinColor="red"
        />

        {/* Current position */}
        {nav.currentPos && nav.navMode !== 'UNKNOWN' && (
          <Marker
            coordinate={{
              latitude: nav.currentPos.lat,
              longitude: nav.currentPos.lon,
            }}
            title="You"
            pinColor={modeColor[nav.navMode]}
          />
        )}
      </MapView>

      {/* No-signal warning banner */}
      {nav.navMode === 'UNKNOWN' && (
        <View style={styles.warningBanner}>
          <Text style={styles.warningText}>
            No sensor data available — check GPS and sensors
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
          </Text>
        </View>
      )}

<<<<<<< HEAD
      {/* Off-route warning */}
      {nav.offRoute && nav.navMode !== 'UNKNOWN' && (
        <View style={styles.offRouteBanner}>
          <Text style={styles.warningText}>Off route — recalculating…</Text>
        </View>
      )}

      {/* Top instruction bar */}
=======
      {/* Instruction bar */}
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
      <View style={[styles.instructionBar, {paddingTop: insets.top + 8}]}>
        <View style={styles.instructionRow}>
          <View
            style={[
              styles.modeBadge,
<<<<<<< HEAD
              {backgroundColor: MODE_COLOR[nav.navMode]},
            ]}>
            <Text style={styles.modeBadgeText}>{MODE_LABEL[nav.navMode]}</Text>
=======
              {backgroundColor: modeColor[nav.navMode]},
            ]}>
            <Text style={styles.modeBadgeText}>{modeLabel[nav.navMode]}</Text>
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
          </View>
          {nav.offRoute && (
            <View style={styles.offRouteBadge}>
              <Text style={styles.offRouteBadgeText}>OFF ROUTE</Text>
            </View>
          )}
<<<<<<< HEAD
=======
          {nav.visionActive && (
            <View style={[styles.visionBadge, styles.visionBadgePulse]}>
              <Text style={styles.visionBadgeText}>
                👁️ VISION: {nav.landmarkName ? nav.landmarkName.toUpperCase() : 'CONFIRMED'}
              </Text>
            </View>
          )}
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
        </View>

        <Text style={styles.instructionText} numberOfLines={2}>
          {nav.instruction}
        </Text>

<<<<<<< HEAD
        {nav.distanceM > 0 && (
          <Text style={styles.distanceText}>
            {nav.distanceM >= 1000
              ? `${(nav.distanceM / 1000).toFixed(1)} km`
              : `${nav.distanceM} m`}
          </Text>
        )}

=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
        {/* Confidence bar */}
        <View style={styles.confBarBg}>
          <View
            style={[
              styles.confBarFill,
              {
                width: `${Math.round(nav.confidence * 100)}%`,
                backgroundColor: nav.confidence > 0.6 ? '#34a853' : '#fbbc04',
              },
            ]}
          />
        </View>
        <Text style={styles.confLabel}>
          Confidence {Math.round(nav.confidence * 100)}%
        </Text>
<<<<<<< HEAD

        <View style={styles.sensorPanel}>
          <Text style={styles.sensorTitle}>
            GPS {nav.navMode === 'GPS' ? 'ON' : 'OFF'} · Sensors{' '}
            {latestIMU ? 'LIVE' : 'WAITING'}
          </Text>
          <Text style={styles.sensorStatusText} numberOfLines={1}>
            {sensorStatus}
          </Text>
          <Text style={styles.drDistanceText}>
            DR distance travelled {formatDistance(nav.drDistanceTravelledM)}
          </Text>
          <View style={styles.sensorGrid}>
            <Text style={styles.sensorText}>
              ACC x {latestIMU ? formatSensor(latestIMU.accel.x) : '--'}
            </Text>
            <Text style={styles.sensorText}>
              y {latestIMU ? formatSensor(latestIMU.accel.y) : '--'}
            </Text>
            <Text style={styles.sensorText}>
              z {latestIMU ? formatSensor(latestIMU.accel.z) : '--'}
            </Text>
          </View>
          <View style={styles.sensorGrid}>
            <Text style={styles.sensorText}>
              GYR x {latestIMU ? formatSensor(latestIMU.gyro.x) : '--'}
            </Text>
            <Text style={styles.sensorText}>
              y {latestIMU ? formatSensor(latestIMU.gyro.y) : '--'}
            </Text>
            <Text style={styles.sensorText}>
              z {latestIMU ? formatSensor(latestIMU.gyro.z) : '--'}
            </Text>
          </View>
        </View>
      </View>

      {/* Recenter button */}
      {nav.currentPos && (
        <Pressable style={styles.recenterButton} onPress={handleRecenter}>
          <Text style={styles.recenterText}>{'\u2316'}</Text>
        </Pressable>
      )}

      {/* Bottom stop button */}
=======
      </View>

      {/* Stop button */}
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 16}]}>
        <Pressable
          style={({pressed}) => [
            styles.stopButton,
            pressed && styles.stopButtonPressed,
          ]}
          onPress={onStop}>
          <Text style={styles.stopButtonText}>Stop Navigation</Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
<<<<<<< HEAD
  container: {flex: 1, backgroundColor: '#e8e0d8'},
=======
  container: {flex: 1, backgroundColor: '#000'},
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

  warningBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: '#ea4335',
    padding: 8,
    alignItems: 'center',
    zIndex: 20,
  },
<<<<<<< HEAD
  offRouteBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: '#f9a825',
    padding: 8,
    alignItems: 'center',
    zIndex: 20,
  },
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  warningText: {color: '#fff', fontWeight: '700', fontSize: 13},

  instructionBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(255,255,255,0.95)',
    paddingHorizontal: 16,
    paddingBottom: 12,
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.15,
    shadowRadius: 6,
  },
  instructionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 6,
  },
  modeBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
<<<<<<< HEAD
  modeBadgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.8},
=======
  modeBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  offRouteBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: '#ea4335',
  },
<<<<<<< HEAD
  offRouteBadgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.8},
  instructionText: {fontSize: 18, fontWeight: '700', color: '#1a1a1a', marginBottom: 4},
  distanceText: {fontSize: 13, color: '#555', marginBottom: 6},
=======
  offRouteBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  instructionText: {
    fontSize: 18,
    fontWeight: '700',
    color: '#1a1a1a',
    marginBottom: 6,
  },
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
  confBarBg: {
    height: 4,
    backgroundColor: '#e0e0e0',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 2,
  },
  confBarFill: {height: 4, borderRadius: 2},
  confLabel: {fontSize: 10, color: '#888'},
<<<<<<< HEAD
  sensorPanel: {
    marginTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#d8d8d8',
    paddingTop: 6,
  },
  sensorTitle: {
    color: '#333',
    fontSize: 10,
    fontWeight: '800',
    marginBottom: 3,
  },
  sensorStatusText: {
    color: '#666',
    fontSize: 10,
    marginBottom: 3,
  },
  drDistanceText: {
    color: '#222',
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 3,
  },
  sensorGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  sensorText: {
    flex: 1,
    color: '#444',
    fontSize: 10,
    fontVariant: ['tabular-nums'],
  },

  recenterButton: {
    position: 'absolute',
    right: 16,
    bottom: 100,
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  recenterText: {fontSize: 24, color: '#1a73e8'},
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

  bottomPanel: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingHorizontal: 24,
    paddingTop: 12,
    backgroundColor: 'rgba(255,255,255,0.95)',
    elevation: 8,
  },
  stopButton: {
    backgroundColor: '#ea4335',
    borderRadius: 14,
    paddingVertical: 16,
    alignItems: 'center',
  },
  stopButtonPressed: {backgroundColor: '#c5221f', transform: [{scale: 0.98}]},
  stopButtonText: {color: '#fff', fontSize: 16, fontWeight: '700'},
<<<<<<< HEAD
=======
  visionBadge: {
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 5,
    backgroundColor: '#34a853',
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#34a853',
    shadowOffset: {width: 0, height: 0},
    shadowOpacity: 0.8,
    shadowRadius: 10,
    elevation: 8,
  },
  visionBadgePulse: {
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.4)',
  },
  visionBadgeText: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 1,
  },
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
});

export default NavigationScreen;
