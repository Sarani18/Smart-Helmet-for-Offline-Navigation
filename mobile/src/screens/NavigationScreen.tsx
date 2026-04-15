/**
 * NavigationScreen
 *
 * Live navigation view. Polls NCS every 2 s via GET /api/navigation/ui/state
 * and renders whatever UIStateMessage the NCS returns:
 *   - OSM tile map (no Google API key needed)
 *   - Route polyline from route_polyline field
 *   - Instruction bar with nav_mode badge and confidence bar
 *   - Bottom panel with stop button
 *
 * route_polyline from NCS is [[lat, lon], ...].
 * react-native-maps UrlTile + Polyline consume {latitude, longitude}.
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MapView, {Marker, Polyline, UrlTile} from 'react-native-maps';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {getUIState, stopNavigation} from '../services/NCSService';
import {NCS_POLL_INTERVAL_MS} from '../services/config';
import {NavMode, PositionMode, UIStateMessage} from '../types';

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Convert UIStateMessage route_polyline [[lat,lon]] to react-native-maps format */
function toLatLng(point: [number, number]) {
  return {latitude: point[0], longitude: point[1]};
}

function formatDistance(m: number): string {
  if (m >= 1000) {return `${(m / 1000).toFixed(1)} km`;}
  return `${Math.round(m)} m`;
}

function modeColor(mode: NavMode): string {
  switch (mode) {
    case NavMode.ONLINE:   return '#27ae60';
    case NavMode.OFFLINE:  return '#e67e22';
    case NavMode.DEGRADED: return '#e74c3c';
  }
}

function modeLabel(mode: NavMode, posMode: PositionMode): string {
  switch (mode) {
    case NavMode.ONLINE:
      return posMode === PositionMode.GPS ? '● GPS · Online' : '● Visual · Online';
    case NavMode.OFFLINE:
      return posMode === PositionMode.VISUAL ? '◎ Visual · Offline' : '◎ GPS · Offline';
    case NavMode.DEGRADED:
      return '⚠ Degraded';
  }
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  sessionId: string;
  initialState: UIStateMessage | null;
  onStop: () => void;
}

const NavigationScreen: React.FC<Props> = ({sessionId, initialState, onStop}) => {
  const insets   = useSafeAreaInsets();
  const mapRef   = useRef<MapView>(null);
  const pollRef  = useRef<ReturnType<typeof setInterval> | null>(null);

  const [navState, setNavState]   = useState<UIStateMessage | null>(initialState);
  const [pollError, setPollError] = useState(false);

  // ── NCS polling ──────────────────────────────────────────────────────────
  const poll = useCallback(async () => {
    try {
      const res = await getUIState(sessionId);
      if (res.accepted && res.ui_state) {
        setNavState(res.ui_state);
        setPollError(false);
      }
    } catch {
      setPollError(true);
    }
  }, [sessionId]);

  useEffect(() => {
    poll(); // Immediate first poll
    pollRef.current = setInterval(poll, NCS_POLL_INTERVAL_MS);
    return () => {
      if (pollRef.current) {clearInterval(pollRef.current);}
    };
  }, [poll]);

  // ── Stop handler ─────────────────────────────────────────────────────────
  const handleStop = useCallback(async () => {
    if (pollRef.current) {clearInterval(pollRef.current);}
    try {
      await stopNavigation(sessionId);
    } catch {
      // best-effort
    }
    onStop();
  }, [sessionId, onStop]);

  // ── Map auto-fit when route first loads ──────────────────────────────────
  useEffect(() => {
    if (!navState || navState.route_polyline.length < 2) {return;}
    const coords = navState.route_polyline.map(toLatLng);
    mapRef.current?.fitToCoordinates(coords, {
      edgePadding: {top: 120, right: 32, bottom: 180, left: 32},
      animated: true,
    });
  }, [navState?.session_id]); // Only fit when session changes (new route)

  // ── Render helpers ───────────────────────────────────────────────────────
  if (!navState) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#1a73e8" />
        <Text style={styles.loadingText}>Waiting for NCS…</Text>
      </View>
    );
  }

  const polyline     = navState.route_polyline.map(toLatLng);
  const originPt     = polyline[0];
  const destPt       = polyline[polyline.length - 1];
  const currentPt    = destPt; // NCS will update as the rider moves
  const color        = modeColor(navState.nav_mode);
  const isArrived    = navState.destination_reached_flag;
  const isOffRoute   = navState.off_route_flag;
  const isDegraded   = navState.nav_mode === NavMode.DEGRADED;

  return (
    <View style={styles.container}>

      {/* ── OSM tile map ── */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFill}
        mapType="none"           // Disable Google base layer
        showsUserLocation={false}
        showsCompass
        rotateEnabled={false}>

        {/* OSM raster tiles — no API key required */}
        <UrlTile
          urlTemplate="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maximumZ={19}
          flipY={false}
          tileSize={256}
        />

        {/* Route polyline */}
        {polyline.length > 1 && (
          <Polyline
            coordinates={polyline}
            strokeColor="#1a73e8"
            strokeWidth={5}
          />
        )}

        {/* Origin pin */}
        {originPt && (
          <Marker coordinate={originPt} title="Start" pinColor="green" />
        )}

        {/* Destination pin */}
        {destPt && originPt !== destPt && (
          <Marker coordinate={destPt} title="Destination" pinColor="red" />
        )}

        {/* Current position dot */}
        {currentPt && (
          <Marker coordinate={currentPt} anchor={{x: 0.5, y: 0.5}}>
            <View style={styles.positionDot} />
          </Marker>
        )}
      </MapView>

      {/* ── Connectivity error ribbon ── */}
      {pollError && (
        <View style={[styles.ribbon, {top: insets.top}]}>
          <Text style={styles.ribbonText}>⚠ NCS unreachable — last known state shown</Text>
        </View>
      )}

      {/* ── Instruction bar (top) ── */}
      <View style={[styles.instructionBar, {paddingTop: insets.top + (pollError ? 36 : 8)}]}>

        {/* Nav mode badge */}
        <View style={[styles.modeBadge, {backgroundColor: color}]}>
          <Text style={styles.modeBadgeText}>
            {modeLabel(navState.nav_mode, navState.position_mode)}
          </Text>
        </View>

        {/* Instruction */}
        {isArrived ? (
          <Text style={styles.instructionText}>🏁 You have arrived!</Text>
        ) : isOffRoute ? (
          <Text style={[styles.instructionText, {color: '#e74c3c'}]}>
            ⚠ Off route — recalculating
          </Text>
        ) : (
          <Text style={styles.instructionText} numberOfLines={2}>
            {navState.next_instruction_text || 'Follow route'}
          </Text>
        )}

        {/* Distance */}
        {!isArrived && navState.distance_to_next_m > 0 && (
          <Text style={styles.distanceText}>
            {formatDistance(navState.distance_to_next_m)}
          </Text>
        )}

        {/* Degraded reason */}
        {isDegraded && navState.degraded_reason && (
          <Text style={styles.degradedReason}>{navState.degraded_reason}</Text>
        )}

        {/* Confidence bar */}
        <View style={styles.confidenceTrack}>
          <View
            style={[
              styles.confidenceFill,
              {
                width: `${Math.round(navState.confidence * 100)}%`,
                backgroundColor:
                  navState.confidence >= 0.6 ? '#27ae60'
                  : navState.confidence >= 0.45 ? '#e67e22'
                  : '#e74c3c',
              },
            ]}
          />
        </View>
        <Text style={styles.confidenceLabel}>
          Confidence {Math.round(navState.confidence * 100)}%
          {' · '}Step {navState.active_step_index}
        </Text>
      </View>

      {/* ── Bottom panel ── */}
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 8}]}>
        <View style={styles.infoRow}>
          <StatBox label="Mode"     value={navState.nav_mode}     color={color} />
          <StatBox label="Position" value={navState.position_mode} />
          <StatBox label="Session"  value={sessionId.slice(-6)}  />
        </View>

        <Pressable
          style={({pressed}) => [styles.stopButton, pressed && styles.stopButtonPressed]}
          onPress={handleStop}>
          <Text style={styles.stopButtonText}>■  Stop Navigation</Text>
        </Pressable>
      </View>
    </View>
  );
};

// ── Small stat box ────────────────────────────────────────────────────────────

interface StatBoxProps {
  label: string;
  value: string | number;
  color?: string;
}
const StatBox: React.FC<StatBoxProps> = ({label, value, color}) => (
  <View style={styles.statBox}>
    <Text style={styles.statLabel}>{label}</Text>
    <Text style={[styles.statValue, color ? {color} : undefined]}>{value}</Text>
  </View>
);

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#e8e8e8'},

  loadingContainer: {
    flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8f9fa',
  },
  loadingText: {marginTop: 12, color: '#555', fontSize: 14},

  // Connection error ribbon
  ribbon: {
    position: 'absolute',
    left: 0, right: 0,
    backgroundColor: '#e74c3c',
    paddingVertical: 6,
    alignItems: 'center',
    zIndex: 99,
  },
  ribbonText: {color: '#fff', fontSize: 12, fontWeight: '600'},

  // ── Instruction bar
  instructionBar: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomLeftRadius: 16,
    borderBottomRightRadius: 16,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.15,
    shadowRadius: 6,
    elevation: 8,
  },
  modeBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: 20,
    marginBottom: 8,
  },
  modeBadgeText: {color: '#fff', fontSize: 11, fontWeight: '700', letterSpacing: 0.4},
  instructionText: {fontSize: 20, fontWeight: '700', color: '#1a1a1a', marginBottom: 4},
  distanceText:    {fontSize: 14, color: '#555', marginBottom: 6},
  degradedReason:  {fontSize: 11, color: '#e74c3c', marginBottom: 4},
  confidenceTrack: {
    height: 4, backgroundColor: '#e0e0e0', borderRadius: 2,
    overflow: 'hidden', marginBottom: 4,
  },
  confidenceFill: {height: 4, borderRadius: 2},
  confidenceLabel: {fontSize: 10, color: '#888'},

  // ── Current position dot
  positionDot: {
    width: 18, height: 18, borderRadius: 9,
    backgroundColor: '#1a73e8',
    borderWidth: 3, borderColor: '#fff',
    shadowColor: '#1a73e8',
    shadowOffset: {width: 0, height: 0},
    shadowOpacity: 0.6, shadowRadius: 4,
    elevation: 4,
  },

  // ── Bottom panel
  bottomPanel: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingTop: 12, paddingHorizontal: 16,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: -2},
    shadowOpacity: 0.1, shadowRadius: 6,
    elevation: 8,
  },
  infoRow: {flexDirection: 'row', justifyContent: 'space-around', marginBottom: 12},
  statBox: {alignItems: 'center'},
  statLabel: {fontSize: 10, color: '#888', marginBottom: 2},
  statValue: {fontSize: 13, fontWeight: '600', color: '#1a1a1a'},
  stopButton: {
    backgroundColor: '#e74c3c', borderRadius: 12,
    paddingVertical: 14, alignItems: 'center',
  },
  stopButtonPressed: {backgroundColor: '#c0392b'},
  stopButtonText: {color: '#fff', fontSize: 16, fontWeight: '700', letterSpacing: 0.3},
});

export default NavigationScreen;
