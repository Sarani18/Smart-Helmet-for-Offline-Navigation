/**
 * NavigationScreen
 *
 * Live navigation using MapLibre GL + OSM tiles.
 * The position coordinator acts as the app-side NCS layer:
 * GPS drives the UI while available; when GPS is lost, NCS activates DR,
 * marks Vision unavailable, and feeds DR coordinates back to the map.
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import * as gpsService from '../services/gpsService';
import * as sensorService from '../services/sensorService';
import * as bleService from '../services/bleService';
import * as helmetWifiService from '../services/helmetWifiService';
import * as navigationEngine from '../services/navigationEngine';
import {
  startCoordinator,
  stopCoordinator,
  addPositionListener,
  type CoordinatorPosition,
  type PositionMode,
  type VisionStatus,
} from '../services/positionCoordinator';
import {downloadTilesAroundPoint} from '../services/tileService';
import MapLibreView from '../components/MapLibreView';
import type {MapLibreViewRef} from '../components/MapLibreView';
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
  drDistanceTravelledM: number;
  navMode: NavMode;
  confidence: number;
  offRoute: boolean;
  destinationReached: boolean;
  currentPos: LatLon | null;
  drActive: boolean;
  visionStatus: VisionStatus;
  visionMessage: string;
  ncsStatus: string;
}

const INITIAL_NAV: NavDisplay = {
  instruction: 'Acquiring position...',
  distanceM: 0,
  drDistanceTravelledM: 0,
  navMode: 'UNKNOWN',
  confidence: 0,
  offRoute: false,
  destinationReached: false,
  currentPos: null,
  drActive: false,
  visionStatus: 'IDLE',
  visionMessage: 'Vision idle',
  ncsStatus: 'Waiting for GPS',
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
};

const NavigationScreen: React.FC<Props> = ({
  sessionId,
  route,
  origin,
  dest,
  onStop,
}) => {
  const insets = useSafeAreaInsets();
  const mapRef = useRef<MapLibreViewRef>(null);
  const [nav, setNav] = useState<NavDisplay>(INITIAL_NAV);
  const [latestIMU, setLatestIMU] = useState<sensorService.IMUReading | null>(null);
  const [sensorStatus, setSensorStatus] = useState(sensorService.getSensorStatus());
  const firstFixDone = useRef(false);
  const arrivedShown = useRef(false);
  const autoFollowMap = useRef(true);

  const routeCoords = useRef<[number, number][]>(
    route.polyline.map(p => [p.lon, p.lat]),
  );

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

  const handlePosition = useCallback(
    (pos: CoordinatorPosition) => {
      if (pos.lat === 0 && pos.lon === 0 && pos.positionMode === 'UNKNOWN') {
        setNav(prev => ({
          ...prev,
          navMode: 'UNKNOWN',
          confidence: 0,
          drActive: pos.drActive,
          visionStatus: pos.visionStatus,
          visionMessage: pos.visionMessage,
          ncsStatus: pos.ncsStatus,
          drDistanceTravelledM: pos.drDistanceTravelledM,
          instruction: 'No GPS or DR position yet',
        }));
        return;
      }

      const state = navigationEngine.updatePosition(pos.lat, pos.lon);
      const navMode: NavMode =
        pos.positionMode === 'GPS'
          ? 'GPS'
          : pos.positionMode === 'DR'
          ? 'DR'
          : 'UNKNOWN';

      setNav({
        instruction: state.nextInstructionText,
        distanceM: state.distanceToNextM,
        drDistanceTravelledM: pos.drDistanceTravelledM,
        navMode,
        confidence: pos.confidence,
        offRoute: state.offRoute,
        destinationReached: state.destinationReached,
        currentPos: {lat: pos.lat, lon: pos.lon},
        drActive: pos.drActive,
        visionStatus: pos.visionStatus,
        visionMessage: pos.visionMessage,
        ncsStatus: pos.ncsStatus,
      });

      mapRef.current?.send({
        type: 'setRider',
        lon: pos.lon,
        lat: pos.lat,
        color: MODE_COLOR[pos.positionMode],
      });

      if (pos.positionMode !== 'UNKNOWN' && autoFollowMap.current) {
        mapRef.current?.send({
          type: 'flyTo',
          lon: pos.lon,
          lat: pos.lat,
          zoom: 15,
        });
      }

      if (bleService.isBLEConnected()) {
        bleService.sendNavInstruction(state.nextInstructionText, state.distanceToNextM);
        bleService.sendGPSStatus(pos.positionMode === 'GPS');
      }
      helmetWifiService.sendNavigationCue({
        instructionText: state.nextInstructionText,
        distanceToNextM: state.distanceToNextM,
        offRoute: state.offRoute,
        destinationReached: state.destinationReached,
      });

      if (!firstFixDone.current && pos.positionMode === 'GPS') {
        firstFixDone.current = true;
        downloadTilesAroundPoint({lat: pos.lat, lon: pos.lon}, 2, [14, 15]).catch(
          e => console.warn('Tile download around current location failed:', e),
        );
      }

      if (state.destinationReached && !arrivedShown.current) {
        arrivedShown.current = true;
        Alert.alert('Arrived!', 'You have reached your destination.', [
          {text: 'OK', onPress: onStop},
        ]);
      }
    },
    [onStop],
  );

  useEffect(() => {
    navigationEngine.loadRoute(route);
    gpsService.startGPS();
    startCoordinator({
      sessionId,
      origin,
      destination: dest,
      routePolyline: route.polyline,
    });

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
      bleService.stopBLE();
      helmetWifiService.clearHelmet();
      helmetWifiService.resetHelmetCommandCache();
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

  const signalWarning =
    nav.navMode === 'UNKNOWN'
      ? sensorService.getSensorError()
        ? `Sensor error: ${sensorService.getSensorError()}`
        : gpsService.getGPSError()
        ? `GPS unavailable: ${gpsService.getGPSError()}`
        : nav.ncsStatus
      : null;

  return (
    <View style={styles.container}>
      <MapLibreView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        initialLon={origin.lon}
        initialLat={origin.lat}
        initialZoom={14}
        onReady={handleMapReady}
        onUserInteraction={handleMapInteraction}
      />

      {signalWarning && (
        <View style={styles.warningBanner}>
          <Text style={styles.warningText}>{signalWarning}</Text>
        </View>
      )}

      {nav.offRoute && nav.navMode !== 'UNKNOWN' && (
        <View style={styles.offRouteBanner}>
          <Text style={styles.warningText}>Off route - recalculating...</Text>
        </View>
      )}

      <View style={[styles.instructionBar, {paddingTop: insets.top + 8}]}>
        <View style={styles.instructionRow}>
          <View
            style={[
              styles.modeBadge,
              {backgroundColor: MODE_COLOR[nav.navMode]},
            ]}>
            <Text style={styles.modeBadgeText}>{MODE_LABEL[nav.navMode]}</Text>
          </View>
          {nav.offRoute && (
            <View style={styles.offRouteBadge}>
              <Text style={styles.offRouteBadgeText}>OFF ROUTE</Text>
            </View>
          )}
        </View>

        <Text style={styles.instructionText} numberOfLines={2}>
          {nav.instruction}
        </Text>

        {nav.distanceM > 0 && (
          <Text style={styles.distanceText}>
            {nav.distanceM >= 1000
              ? `${(nav.distanceM / 1000).toFixed(1)} km`
              : `${nav.distanceM} m`}
          </Text>
        )}

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

        {nav.drActive && (
          <View style={styles.sensorPanel}>
            <Text style={styles.sensorTitle}>
              NCS fallback active
            </Text>
            <Text style={styles.sensorStatusText} numberOfLines={1}>
              {nav.ncsStatus}
            </Text>
            <Text style={styles.sensorStatusText} numberOfLines={1}>
              Vision: {nav.visionStatus.toLowerCase()} - {nav.visionMessage}
            </Text>
            <Text style={styles.drDistanceText}>
              DR distance travelled {formatDistance(nav.drDistanceTravelledM)}
            </Text>
            <Text style={styles.sensorStatusText} numberOfLines={1}>
              Sensors: {sensorStatus}
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
        )}
      </View>

      {nav.currentPos && (
        <Pressable style={styles.recenterButton} onPress={handleRecenter}>
          <Text style={styles.recenterText}>LOC</Text>
        </Pressable>
      )}

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
  container: {flex: 1, backgroundColor: '#e8e0d8'},

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
  modeBadgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.8},
  offRouteBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: '#ea4335',
  },
  offRouteBadgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.8},
  instructionText: {fontSize: 18, fontWeight: '700', color: '#1a1a1a', marginBottom: 4},
  distanceText: {fontSize: 13, color: '#555', marginBottom: 6},
  confBarBg: {
    height: 4,
    backgroundColor: '#e0e0e0',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 2,
  },
  confBarFill: {height: 4, borderRadius: 2},
  confLabel: {fontSize: 10, color: '#888'},
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
  recenterText: {fontSize: 12, color: '#1a73e8', fontWeight: '800'},

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
});

export default NavigationScreen;
