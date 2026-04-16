/**
 * DemoNavigationScreen
 *
 * Plays back DEMO_STEPS one at a time, advancing every STEP_INTERVAL_MS.
 * Uses a pure React Native coordinate renderer instead of react-native-maps
 * so the demo works without a Google Maps API key or network connection.
 *
 * Controls:
 *   ▶/⏸  Play / Pause
 *   ‹ Prev / Next ›  Manual step
 *   Stop  Returns to DemoHomeScreen
 */

import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {
  DEMO_STEPS,
  DEMO_ORIGIN,
  DEMO_DEST,
  FULL_POLYLINE,
  STEP_INTERVAL_MS,
  type NavMode,
  type PositionMode,
  type LatLon,
} from './demoRoute';

interface Props {
  onStop: () => void;
}

const TOTAL = DEMO_STEPS.length;

const MODE_COLOR: Record<NavMode, string> = {
  ONLINE: '#34a853',
  OFFLINE: '#fbbc04',
  DEGRADED: '#ea4335',
};
const POS_COLOR: Record<PositionMode, string> = {
  GPS: '#34a853',
  VISUAL: '#fbbc04',
  UNKNOWN: '#ea4335',
};

// ── coordinate-to-pixel scaler ────────────────────────────────────────────────

function buildScaler(
  points: LatLon[],
  canvasW: number,
  canvasH: number,
  pad: number,
) {
  const lats = points.map(p => p.lat);
  const lons = points.map(p => p.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const rangeW = canvasW - pad * 2;
  const rangeH = canvasH - pad * 2;
  return (p: LatLon) => ({
    x: pad + ((p.lon - minLon) / (maxLon - minLon)) * rangeW,
    y: pad + ((maxLat - p.lat) / (maxLat - minLat)) * rangeH,
  });
}

// ── MiniMap component ─────────────────────────────────────────────────────────

interface MiniMapProps {
  width: number;
  height: number;
  traveledPoints: LatLon[];
  currentPos: LatLon;
  posColor: string;
}

const MiniMap: React.FC<MiniMapProps> = ({
  width,
  height,
  traveledPoints,
  currentPos,
  posColor,
}) => {
  const scaler = useMemo(
    () => buildScaler(FULL_POLYLINE, width, height, 24),
    [width, height],
  );

  // Full route background — sample every 4th point (~93 dots)
  const bgDots = useMemo(() => FULL_POLYLINE.filter((_, i) => i % 4 === 0), []);
  // Traveled portion — sample every 2nd point for denser trail
  const travelDots = useMemo(
    () => traveledPoints.filter((_, i) => i % 2 === 0),
    [traveledPoints],
  );

  const originPx = scaler(DEMO_ORIGIN);
  const destPx = scaler(DEMO_DEST);
  const curPx = scaler(currentPos);

  return (
    <View style={[styles.miniMap, {width, height}]}>
      {/* Full route (faint) */}
      {bgDots.map((p, i) => {
        const {x, y} = scaler(p);
        return (
          <View
            key={`bg${i}`}
            style={[styles.bgDot, {left: x - 2, top: y - 2}]}
          />
        );
      })}

      {/* Traveled portion (bright) */}
      {travelDots.map((p, i) => {
        const {x, y} = scaler(p);
        return (
          <View
            key={`tr${i}`}
            style={[styles.travelDot, {left: x - 2.5, top: y - 2.5}]}
          />
        );
      })}

      {/* Origin */}
      <View
        style={[
          styles.endMarker,
          {backgroundColor: '#34a853', left: originPx.x - 6, top: originPx.y - 6},
        ]}
      />

      {/* Destination */}
      <View
        style={[
          styles.endMarker,
          {backgroundColor: '#ea4335', left: destPx.x - 6, top: destPx.y - 6},
        ]}
      />

      {/* Rider (current position) */}
      <View
        style={[
          styles.riderOuter,
          {left: curPx.x - 11, top: curPx.y - 11},
        ]}>
        <View style={[styles.riderInner, {backgroundColor: posColor}]} />
      </View>
    </View>
  );
};

// ── Screen ────────────────────────────────────────────────────────────────────

const DemoNavigationScreen: React.FC<Props> = ({onStop}) => {
  const insets = useSafeAreaInsets();
  const {width, height} = useWindowDimensions();
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [stepIdx, setStepIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const arrivedShown = useRef(false);

  const step = DEMO_STEPS[stepIdx];
  const currentPos = step.routePolyline[step.routePolyline.length - 1];
  const isCrash = step.nextInstructionText.includes('CRASH');

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const advance = useCallback(() => {
    setStepIdx(prev => {
      const next = prev + 1;
      if (next >= TOTAL) {
        clearTimer();
        return prev;
      }
      return next;
    });
  }, [clearTimer]);

  // Auto-advance timer
  useEffect(() => {
    if (playing && !step.destinationReached) {
      timerRef.current = setInterval(advance, STEP_INTERVAL_MS);
    } else {
      clearTimer();
    }
    return clearTimer;
  }, [playing, step.destinationReached, advance, clearTimer]);

  // Show arrived alert once
  useEffect(() => {
    if (step.destinationReached && !arrivedShown.current) {
      arrivedShown.current = true;
      clearTimer();
      Alert.alert(
        'Demo Complete',
        'You have arrived at IGI Airport T3 Metro Station.\n\nDemo trip finished.',
        [{text: 'Back to Home', onPress: onStop}],
      );
    }
  }, [step.destinationReached, onStop, clearTimer]);

  // Map height = screen minus top instruction bar and bottom controls (rough estimate)
  const mapHeight = height - insets.top - insets.bottom - 180;

  return (
    <View style={styles.container}>
      {/* Mini-map fills the background */}
      <MiniMap
        width={width}
        height={mapHeight + insets.top + 60}
        traveledPoints={step.routePolyline}
        currentPos={currentPos}
        posColor={POS_COLOR[step.positionMode]}
      />

      {/* Crash overlay */}
      {isCrash && (
        <View style={styles.crashBanner}>
          <Text style={styles.crashText}>{'CRASH DETECTED — SOS SENT'}</Text>
        </View>
      )}

      {/* Off-route banner */}
      {step.offRoute && !isCrash && (
        <View style={styles.offRouteBanner}>
          <Text style={styles.offRouteText}>{'OFF ROUTE — Recalculating...'}</Text>
        </View>
      )}

      {/* Top instruction bar */}
      <View style={[styles.instructionBar, {paddingTop: insets.top + 6}]}>
        <View style={styles.badgeRow}>
          <View style={[styles.badge, {backgroundColor: MODE_COLOR[step.navMode]}]}>
            <Text style={styles.badgeText}>{step.navMode}</Text>
          </View>
          <View style={[styles.badge, {backgroundColor: POS_COLOR[step.positionMode]}]}>
            <Text style={styles.badgeText}>{step.positionMode}</Text>
          </View>
          <Text style={styles.stepCounter}>
            {step.activeStepIndex + 1} / {TOTAL}
          </Text>
        </View>

        <Text style={styles.instructionText} numberOfLines={2}>
          {step.nextInstructionText}
        </Text>

        {step.distanceToNextM > 0 && (
          <Text style={styles.distanceText}>
            {step.distanceToNextM >= 1000
              ? `${(step.distanceToNextM / 1000).toFixed(1)} km`
              : `${step.distanceToNextM} m`}
          </Text>
        )}

        {/* Confidence bar */}
        <View style={styles.confBarBg}>
          <View
            style={[
              styles.confBarFill,
              {
                width: `${Math.round(step.confidence * 100)}%` as `${number}%`,
                backgroundColor:
                  step.confidence > 0.6
                    ? '#34a853'
                    : step.confidence > 0.35
                    ? '#fbbc04'
                    : '#ea4335',
              },
            ]}
          />
        </View>
        <Text style={styles.confLabel}>
          Confidence {Math.round(step.confidence * 100)}%
        </Text>
      </View>

      {/* Bottom controls */}
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 12}]}>
        {/* Progress bar */}
        <View style={styles.progressBg}>
          <View
            style={[
              styles.progressFill,
              {width: `${((stepIdx + 1) / TOTAL) * 100}%` as `${number}%`},
            ]}
          />
        </View>

        <View style={styles.controls}>
          <Pressable
            style={({pressed}) => [styles.ctrlBtn, pressed && styles.ctrlBtnPressed]}
            onPress={() => setStepIdx(prev => Math.max(0, prev - 1))}
            disabled={stepIdx === 0}>
            <Text style={[styles.ctrlText, stepIdx === 0 && styles.ctrlDisabled]}>
              {'‹ Prev'}
            </Text>
          </Pressable>

          <Pressable
            style={({pressed}) => [
              styles.playPauseBtn,
              pressed && styles.playPauseBtnPressed,
            ]}
            onPress={() => setPlaying(p => !p)}>
            <Text style={styles.playPauseText}>{playing ? '⏸' : '▶'}</Text>
          </Pressable>

          <Pressable
            style={({pressed}) => [styles.ctrlBtn, pressed && styles.ctrlBtnPressed]}
            onPress={() => setStepIdx(prev => Math.min(TOTAL - 1, prev + 1))}
            disabled={stepIdx === TOTAL - 1}>
            <Text
              style={[styles.ctrlText, stepIdx === TOTAL - 1 && styles.ctrlDisabled]}>
              {'Next ›'}
            </Text>
          </Pressable>
        </View>

        <Pressable
          style={({pressed}) => [
            styles.stopButton,
            pressed && styles.stopButtonPressed,
          ]}
          onPress={onStop}>
          <Text style={styles.stopButtonText}>Stop Demo</Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#0d1b2a'},

  miniMap: {backgroundColor: '#0d1b2a', position: 'relative'},
  bgDot: {
    position: 'absolute',
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(26,115,232,0.25)',
  },
  travelDot: {
    position: 'absolute',
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: 'rgba(26,115,232,0.9)',
  },
  endMarker: {
    position: 'absolute',
    width: 12,
    height: 12,
    borderRadius: 6,
    borderWidth: 2,
    borderColor: '#fff',
  },
  riderOuter: {
    position: 'absolute',
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderWidth: 2,
    borderColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
  },
  riderInner: {width: 12, height: 12, borderRadius: 6},

  crashBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: '#ea4335',
    padding: 10,
    alignItems: 'center',
    zIndex: 30,
  },
  crashText: {
    color: '#fff',
    fontWeight: '900',
    fontSize: 15,
    letterSpacing: 0.5,
  },
  offRouteBanner: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: '#f9a825',
    padding: 8,
    alignItems: 'center',
    zIndex: 30,
  },
  offRouteText: {color: '#4a3000', fontWeight: '800', fontSize: 13},

  instructionBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(255,255,255,0.96)',
    paddingHorizontal: 16,
    paddingBottom: 10,
    elevation: 8,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.14,
    shadowRadius: 6,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 6,
  },
  badge: {borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3},
  badgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.5},
  stepCounter: {marginLeft: 'auto', fontSize: 11, color: '#888'},
  instructionText: {
    fontSize: 17,
    fontWeight: '700',
    color: '#1a1a1a',
    marginBottom: 4,
  },
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

  bottomPanel: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingHorizontal: 20,
    paddingTop: 12,
    elevation: 10,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: -2},
    shadowOpacity: 0.12,
    shadowRadius: 6,
  },
  progressBg: {
    height: 3,
    backgroundColor: '#e0e0e0',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 12,
  },
  progressFill: {height: 3, backgroundColor: '#1a73e8', borderRadius: 2},
  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  ctrlBtn: {paddingHorizontal: 16, paddingVertical: 8},
  ctrlBtnPressed: {opacity: 0.6},
  ctrlText: {fontSize: 15, color: '#1a73e8', fontWeight: '600'},
  ctrlDisabled: {color: '#ccc'},
  playPauseBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: '#1a73e8',
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
  },
  playPauseBtnPressed: {backgroundColor: '#1558b0'},
  playPauseText: {fontSize: 22, color: '#fff'},
  stopButton: {
    backgroundColor: '#ea4335',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    elevation: 2,
  },
  stopButtonPressed: {backgroundColor: '#c5221f', transform: [{scale: 0.98}]},
  stopButtonText: {color: '#fff', fontSize: 15, fontWeight: '700'},
});

export default DemoNavigationScreen;
