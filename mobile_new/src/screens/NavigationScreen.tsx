/**
 * NavigationScreen
 *
 * Standalone live navigation — no NCS server needed.
 * On mount: starts GPS, IMU sensors, DR, BLE, and position coordinator.
 * Position coordinator feeds navigation engine every 500ms.
 * MapView renders offline OSM tiles from DocumentDirectoryPath.
 *
 * Sensor failure policy:
 *   GPS lost   → DR mode (DEGRADED badge)
 *   All down   → UNKNOWN badge + warning banner — app stays open, does NOT crash
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  Alert,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MapView, {
  LocalTile,
  Marker,
  Polyline,
  type Region,
} from 'react-native-maps';
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
import {getTileTemplate} from '../services/tileService';
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
  navMode: NavMode;
  confidence: number;
  offRoute: boolean;
  destinationReached: boolean;
  currentPos: LatLon | null;
}

const INITIAL_NAV: NavDisplay = {
  instruction: 'Acquiring position…',
  distanceM: 0,
  navMode: 'UNKNOWN',
  confidence: 0,
  offRoute: false,
  destinationReached: false,
  currentPos: null,
};

const NavigationScreen: React.FC<Props> = ({
  sessionId: _sessionId,
  route,
  origin,
  dest,
  onStop,
}) => {
  const insets = useSafeAreaInsets();
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

  const handlePosition = useCallback(
    (pos: CoordinatorPosition) => {
      if (pos.lat === 0 && pos.lon === 0 && pos.positionMode === 'UNKNOWN') {
        setNav(prev => ({
          ...prev,
          navMode: 'UNKNOWN',
          confidence: 0,
          instruction: 'No sensor data — check GPS and sensors',
        }));
        return;
      }

      const state = navigationEngine.updatePosition(pos.lat, pos.lon);

      const navMode: NavMode = pos.positionMode === 'GPS'
        ? 'GPS'
        : pos.positionMode === 'DR'
        ? 'DR'
        : 'UNKNOWN';

      setNav({
        instruction: state.nextInstructionText,
        distanceM: state.distanceToNextM,
        navMode,
        confidence: pos.confidence,
        offRoute: state.offRoute,
        destinationReached: state.destinationReached,
        currentPos: {lat: pos.lat, lon: pos.lon},
      });

      // Notify helmet via BLE
      if (bleService.isBLEConnected()) {
        bleService.sendNavInstruction(state.nextInstructionText, state.distanceToNextM);
        bleService.sendGPSStatus(pos.positionMode === 'GPS');
      }

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
        Alert.alert('Arrived!', 'You have reached your destination.', [
          {text: 'OK', onPress: onStop},
        ]);
      }
    },
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
          </Text>
        </View>
      )}

      {/* Instruction bar */}
      <View style={[styles.instructionBar, {paddingTop: insets.top + 8}]}>
        <View style={styles.instructionRow}>
          <View
            style={[
              styles.modeBadge,
              {backgroundColor: modeColor[nav.navMode]},
            ]}>
            <Text style={styles.modeBadgeText}>{modeLabel[nav.navMode]}</Text>
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
      </View>

      {/* Stop button */}
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
  container: {flex: 1, backgroundColor: '#000'},

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
  modeBadgeText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  offRouteBadge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: '#ea4335',
  },
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
  confBarBg: {
    height: 4,
    backgroundColor: '#e0e0e0',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 2,
  },
  confBarFill: {height: 4, borderRadius: 2},
  confLabel: {fontSize: 10, color: '#888'},

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
