/**
 * NavigationScreen
 *
 * Live navigation view.  Polls NCS every 2 s for UIStateMessage and renders:
 *   - OSM raster tile map (no Google API key)
 *   - Route polyline + origin / destination pins
 *   - Live position dot: blue = GPS, orange = dead reckoning, grey = no fix
 *   - Instruction bar with nav_mode badge and confidence bar
 *   - Bottom panel: mode stats, GPS status, BLE status, stop button
 *
 * GPS state arrives as a prop from App.tsx (GPS is an always-on daemon there).
 * Dead-reckoning runs inside this screen; it registers its anchor() callback
 * with the parent via onRegisterAnchor so GPS fixes flow in automatically.
 *
 * BLE gateway (useBluetooth):
 *   - Scans for SmartHelmet on mount
 *   - Sends NAV_INSTRUCTION to helmet whenever the step/instruction changes
 *   - Sends LED_OFF when active_step_index advances (turn confirmed by NCS)
 *   - Sends NOP + new instruction when off_route_flag fires (wrong turn)
 *   - Sends GPS_STATUS whenever gpsState.gpsLost changes
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MapView, {Marker, Polyline, UrlTile} from 'react-native-maps';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {getUIState, stopNavigation} from '../services/NCSService';
import {NCS_POLL_INTERVAL_MS} from '../services/config';
import {
  InstructionCode,
  NavMode,
  PositionMode,
  Position,
  UIStateMessage,
} from '../types';
import {GPSState} from '../hooks/useGPS';
import {useDeadReckoning} from '../hooks/useDeadReckoning';
import {useBluetooth} from '../hooks/useBluetooth';
import {ConnectionState} from '../types';

// ── Helpers ──────────────────────────────────────────────────────────────────

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
    case NavMode.ONLINE:   return posMode === PositionMode.GPS ? '● GPS · Online' : '● Visual · Online';
    case NavMode.OFFLINE:  return posMode === PositionMode.VISUAL ? '◎ Visual · Offline' : '◎ GPS · Offline';
    case NavMode.DEGRADED: return '⚠ Degraded';
  }
}

/**
 * Map NCS instruction text → InstructionCode for the helmet LED.
 * Uses keyword matching on the text NCS/OSRM returns.
 */
function textToCode(text: string): InstructionCode {
  const t = text.toLowerCase();
  if (t.includes('u-turn') || t.includes('uturn'))  {return InstructionCode.U_TURN;}
  if (t.includes('left'))                            {return InstructionCode.TURN_LEFT;}
  if (t.includes('right'))                           {return InstructionCode.TURN_RIGHT;}
  if (t.includes('arrived') || t.includes('destination') || t.includes('arrive')) {
    return InstructionCode.ARRIVE;
  }
  return InstructionCode.GO_STRAIGHT;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface Props {
  sessionId:         string;
  initialState:      UIStateMessage | null;
  /** GPS state from the always-on daemon in App.tsx */
  gpsState:          GPSState;
  /** Register the DR anchor() so App.tsx can forward GPS fixes into DR */
  onRegisterAnchor:  (fn: ((lat: number, lon: number, speed: number) => void) | null) => void;
  onStop:            () => void;
}

const NavigationScreen: React.FC<Props> = ({
  sessionId, initialState, gpsState, onRegisterAnchor, onStop,
}) => {
  const insets  = useSafeAreaInsets();
  const mapRef  = useRef<MapView>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [navState, setNavState]   = useState<UIStateMessage | null>(initialState);
  const [pollError, setPollError] = useState(false);

  // Live rider position: GPS → DR fallback
  const [riderPos, setRiderPos] = useState<{latitude: number; longitude: number} | null>(null);

  // ── Dead-reckoning ────────────────────────────────────────────────────────
  const {state: drState, anchor, updateSpeed} = useDeadReckoning(sessionId, gpsState.drActive, {
    onPosition: useCallback((position: Position) => {
      if (gpsState.gpsLost) {
        setRiderPos({latitude: position.latitude, longitude: position.longitude});
      }
    }, [gpsState.gpsLost]),
  });

  // Register anchor with App.tsx so GPS fixes flow here
  useEffect(() => {
    onRegisterAnchor(anchor);
    return () => {onRegisterAnchor(null);};
  }, [anchor, onRegisterAnchor]);

  // Mirror GPS position when available
  useEffect(() => {
    if (gpsState.position && !gpsState.gpsLost) {
      setRiderPos({latitude: gpsState.position.latitude, longitude: gpsState.position.longitude});
      updateSpeed(gpsState.position.speed);
    }
  }, [gpsState.position, gpsState.gpsLost, updateSpeed]);

  // ── BLE gateway ───────────────────────────────────────────────────────────
  const ble = useBluetooth(sessionId);

  // Auto-scan on mount — helmet may already be nearby
  useEffect(() => {
    ble.scan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── BLE: sync GPS status changes to helmet ────────────────────────────────
  const prevGpsLostRef = useRef(false);
  useEffect(() => {
    if (gpsState.gpsLost !== prevGpsLostRef.current) {
      ble.sendGPSStatus(!gpsState.gpsLost);
      prevGpsLostRef.current = gpsState.gpsLost;
    }
  }, [gpsState.gpsLost, ble]);

  // ── BLE: send instructions to helmet on step / instruction changes ────────
  const prevStepRef        = useRef(-1);
  const prevInstructionRef = useRef('');
  const prevOffRouteRef    = useRef(false);

  useEffect(() => {
    if (!navState) {return;}

    const stepAdvanced       = prevStepRef.current !== -1 &&
                               navState.active_step_index !== prevStepRef.current;
    const instructionChanged = navState.next_instruction_text !== prevInstructionRef.current;
    const offRouteStarted    = navState.off_route_flag && !prevOffRouteRef.current;

    if (stepAdvanced) {
      // Turn confirmed (NCS advanced the step) → stop LED indication
      ble.sendLEDOff();
    }

    if (offRouteStarted) {
      // Wrong turn → NOP (halt current indicator) then send next direction
      ble.sendInstruction(InstructionCode.NOP, 0);
    }

    if (instructionChanged || stepAdvanced) {
      const code = textToCode(navState.next_instruction_text);
      ble.sendInstruction(code, navState.distance_to_next_m);
    }

    if (navState.destination_reached_flag && !prevStepRef.current) {
      ble.sendInstruction(InstructionCode.ARRIVE, 0);
    }

    prevStepRef.current        = navState.active_step_index;
    prevInstructionRef.current = navState.next_instruction_text;
    prevOffRouteRef.current    = navState.off_route_flag;
  }, [navState, ble]);

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
    poll();
    pollRef.current = setInterval(poll, NCS_POLL_INTERVAL_MS);
    return () => { if (pollRef.current) {clearInterval(pollRef.current);} };
  }, [poll]);

  // ── Stop handler ─────────────────────────────────────────────────────────
  const handleStop = useCallback(async () => {
    if (pollRef.current) {clearInterval(pollRef.current);}
    ble.sendInstruction(InstructionCode.LED_OFF, 0);
    ble.disconnect();
    try { await stopNavigation(sessionId); } catch {}
    onStop();
  }, [sessionId, onStop, ble]);

  // ── Map auto-fit on new route ─────────────────────────────────────────────
  useEffect(() => {
    if (!navState || navState.route_polyline.length < 2) {return;}
    mapRef.current?.fitToCoordinates(navState.route_polyline.map(toLatLng), {
      edgePadding: {top: 120, right: 32, bottom: 180, left: 32},
      animated: true,
    });
  }, [navState?.session_id]);

  // ── Loading ───────────────────────────────────────────────────────────────
  if (!navState) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#1a73e8" />
        <Text style={styles.loadingText}>Waiting for NCS…</Text>
      </View>
    );
  }

  // ── Derived render values ─────────────────────────────────────────────────
  const polyline   = navState.route_polyline.map(toLatLng);
  const originPt   = polyline[0];
  const destPt     = polyline[polyline.length - 1];
  const currentPt  = riderPos ?? destPt;
  const color      = modeColor(navState.nav_mode);
  const isArrived  = navState.destination_reached_flag;
  const isOffRoute = navState.off_route_flag;
  const isDegraded = navState.nav_mode === NavMode.DEGRADED;
  const posSource  = gpsState.gpsLost
    ? (drState.hasAnchor ? 'DR' : '?')
    : (gpsState.position ? 'GPS' : '…');
  const bleConnected = ble.state.connectionState === ConnectionState.CONNECTED;

  return (
    <View style={styles.container}>

      {/* OSM tile map */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFill}
        mapType="none"
        showsUserLocation={false}
        showsCompass
        rotateEnabled={false}>

        <UrlTile
          urlTemplate="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          maximumZ={19}
          flipY={false}
          tileSize={256}
        />

        {polyline.length > 1 && (
          <Polyline coordinates={polyline} strokeColor="#1a73e8" strokeWidth={5} />
        )}

        {originPt && <Marker coordinate={originPt} title="Start" pinColor="green" />}
        {destPt && originPt !== destPt && (
          <Marker coordinate={destPt} title="Destination" pinColor="red" />
        )}

        {currentPt && (
          <Marker coordinate={currentPt} anchor={{x: 0.5, y: 0.5}}>
            <View style={[
              styles.positionDot,
              gpsState.gpsLost && drState.hasAnchor && styles.positionDotDR,
              gpsState.gpsLost && !drState.hasAnchor && styles.positionDotUnknown,
            ]}>
              <Text style={styles.positionDotLabel}>{posSource}</Text>
            </View>
          </Marker>
        )}
      </MapView>

      {/* NCS connectivity error ribbon */}
      {pollError && (
        <View style={[styles.ribbon, {top: insets.top}]}>
          <Text style={styles.ribbonText}>⚠ NCS unreachable — last known state shown</Text>
        </View>
      )}

      {/* Instruction bar */}
      <View style={[styles.instructionBar, {paddingTop: insets.top + (pollError ? 36 : 8)}]}>

        <View style={[styles.modeBadge, {backgroundColor: color}]}>
          <Text style={styles.modeBadgeText}>
            {modeLabel(navState.nav_mode, navState.position_mode)}
          </Text>
        </View>

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

        {!isArrived && navState.distance_to_next_m > 0 && (
          <Text style={styles.distanceText}>{formatDistance(navState.distance_to_next_m)}</Text>
        )}

        {isDegraded && navState.degraded_reason && (
          <Text style={styles.degradedReason}>{navState.degraded_reason}</Text>
        )}

        <View style={styles.confidenceTrack}>
          <View style={[styles.confidenceFill, {
            width: `${Math.round(navState.confidence * 100)}%`,
            backgroundColor:
              navState.confidence >= 0.6 ? '#27ae60'
              : navState.confidence >= 0.45 ? '#e67e22'
              : '#e74c3c',
          }]} />
        </View>
        <Text style={styles.confidenceLabel}>
          Confidence {Math.round(navState.confidence * 100)}%
          {' · '}Step {navState.active_step_index}
        </Text>
      </View>

      {/* Bottom panel */}
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 8}]}>
        <View style={styles.infoRow}>
          <StatBox label="Mode"     value={navState.nav_mode}      color={color} />
          <StatBox
            label="GPS"
            value={gpsState.gpsLost ? `Lost (${gpsState.deadCount})` : 'Active'}
            color={gpsState.gpsLost ? '#e74c3c' : '#27ae60'}
          />
          <StatBox
            label="Helmet"
            value={bleConnected ? (ble.state.linkHealthy ? 'Linked' : 'Weak') : 'No BLE'}
            color={bleConnected ? (ble.state.linkHealthy ? '#27ae60' : '#e67e22') : '#888'}
          />
          <StatBox label="Session"  value={sessionId.slice(-6)} />
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

// ── StatBox ───────────────────────────────────────────────────────────────────

interface StatBoxProps {label: string; value: string | number; color?: string}
const StatBox: React.FC<StatBoxProps> = ({label, value, color}) => (
  <View style={styles.statBox}>
    <Text style={styles.statLabel}>{label}</Text>
    <Text style={[styles.statValue, color ? {color} : undefined]}>{String(value)}</Text>
  </View>
);

// ── Styles ────────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container:        {flex: 1, backgroundColor: '#e8e8e8'},
  loadingContainer: {flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8f9fa'},
  loadingText:      {marginTop: 12, color: '#555', fontSize: 14},

  ribbon: {
    position: 'absolute', left: 0, right: 0,
    backgroundColor: '#e74c3c', paddingVertical: 6,
    alignItems: 'center', zIndex: 99,
  },
  ribbonText: {color: '#fff', fontSize: 12, fontWeight: '600'},

  instructionBar: {
    position: 'absolute', top: 0, left: 0, right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingHorizontal: 16, paddingBottom: 12,
    borderBottomLeftRadius: 16, borderBottomRightRadius: 16,
    shadowColor: '#000', shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.15, shadowRadius: 6, elevation: 8,
  },
  modeBadge: {
    alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 3,
    borderRadius: 20, marginBottom: 8,
  },
  modeBadgeText:  {color: '#fff', fontSize: 11, fontWeight: '700', letterSpacing: 0.4},
  instructionText:{fontSize: 20, fontWeight: '700', color: '#1a1a1a', marginBottom: 4},
  distanceText:   {fontSize: 14, color: '#555', marginBottom: 6},
  degradedReason: {fontSize: 11, color: '#e74c3c', marginBottom: 4},
  confidenceTrack:{height: 4, backgroundColor: '#e0e0e0', borderRadius: 2, overflow: 'hidden', marginBottom: 4},
  confidenceFill: {height: 4, borderRadius: 2},
  confidenceLabel:{fontSize: 10, color: '#888'},

  positionDot: {
    width: 28, height: 28, borderRadius: 14,
    backgroundColor: '#1a73e8',
    borderWidth: 3, borderColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
    shadowColor: '#1a73e8', shadowOffset: {width: 0, height: 0},
    shadowOpacity: 0.6, shadowRadius: 4, elevation: 4,
  },
  positionDotDR:      {backgroundColor: '#e67e22', shadowColor: '#e67e22'},
  positionDotUnknown: {backgroundColor: '#888',    shadowColor: '#888'},
  positionDotLabel:   {fontSize: 7, fontWeight: '800', color: '#fff', letterSpacing: 0.2},

  bottomPanel: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingTop: 12, paddingHorizontal: 16,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    shadowColor: '#000', shadowOffset: {width: 0, height: -2},
    shadowOpacity: 0.1, shadowRadius: 6, elevation: 8,
  },
  infoRow:   {flexDirection: 'row', justifyContent: 'space-around', marginBottom: 12},
  statBox:   {alignItems: 'center'},
  statLabel: {fontSize: 10, color: '#888', marginBottom: 2},
  statValue: {fontSize: 13, fontWeight: '600', color: '#1a1a1a'},
  stopButton: {
    backgroundColor: '#e74c3c', borderRadius: 12,
    paddingVertical: 14, alignItems: 'center',
  },
  stopButtonPressed: {backgroundColor: '#c0392b'},
  stopButtonText:    {color: '#fff', fontSize: 16, fontWeight: '700', letterSpacing: 0.3},
});

export default NavigationScreen;
