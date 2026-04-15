/**
 * DemoNavigationScreen
 *
 * Plays back DEMO_STEPS one at a time, advancing every STEP_INTERVAL_MS.
 * The map pans to the current rider position (last point of the growing polyline).
 * Shows instruction bar, mode badges, confidence bar, off-route / crash / arrival
 * overlays — exactly the same UI as real NavigationScreen but driven by static data.
 *
 * Controls:
 *   ▶/⏸  Play / Pause
 *   ‹ Prev / Next ›  Manual step
 *   Recenter button  Snaps map back to current position
 *   Stop  Returns to DemoHomeScreen
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MapView, {Marker, Polyline, UrlTile} from 'react-native-maps';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {
  DEMO_STEPS,
  DEMO_ORIGIN,
  DEMO_DEST,
  STEP_INTERVAL_MS,
  type NavMode,
  type PositionMode,
} from './demoRoute';
import {TILE_CACHE_DIR} from '../services/tileService';

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

const DemoNavigationScreen: React.FC<Props> = ({onStop}) => {
  const insets = useSafeAreaInsets();
  const mapRef = useRef<MapView>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [stepIdx, setStepIdx] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [mapReady, setMapReady] = useState(false);
  const arrivedShown = useRef(false);

  const step = DEMO_STEPS[stepIdx];
  const currentPos = step.routePolyline[step.routePolyline.length - 1];

  // Pan map to current rider position whenever step changes
  useEffect(() => {
    if (mapReady && mapRef.current) {
      mapRef.current.animateToRegion(
        {
          latitude: currentPos.lat,
          longitude: currentPos.lon,
          latitudeDelta: 0.012,
          longitudeDelta: 0.012,
        },
        400,
      );
    }
  }, [stepIdx, mapReady, currentPos.lat, currentPos.lon]);

  // Show arrived alert once
  useEffect(() => {
    if (step.destinationReached && !arrivedShown.current) {
      arrivedShown.current = true;
      clearTimer();
      Alert.alert(
        '🏁 Demo Complete',
        'You have arrived at IGI Airport T3 Metro Station.\n\nDemo trip finished.',
        [{text: 'Back to Home', onPress: onStop}],
      );
    }
  }, [step.destinationReached, onStop]);

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

  const handlePrev = () => {
    setStepIdx(prev => Math.max(0, prev - 1));
  };
  const handleNext = () => {
    setStepIdx(prev => Math.min(TOTAL - 1, prev + 1));
  };
  const handleRecenter = () => {
    mapRef.current?.animateToRegion(
      {
        latitude: currentPos.lat,
        longitude: currentPos.lon,
        latitudeDelta: 0.012,
        longitudeDelta: 0.012,
      },
      400,
    );
  };

  const polyCoords = step.routePolyline.map(p => ({
    latitude: p.lat,
    longitude: p.lon,
  }));

  const isCrash = step.nextInstructionText.includes('CRASH');

  return (
    <View style={styles.container}>
      {/* Map */}
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFillObject}
        mapType="none"
        provider={undefined}
        rotateEnabled={false}
        initialRegion={{
          latitude: DEMO_ORIGIN.lat,
          longitude: DEMO_ORIGIN.lon,
          latitudeDelta: 0.02,
          longitudeDelta: 0.02,
        }}
        onMapReady={() => setMapReady(true)}>
        <UrlTile
          urlTemplate="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          tileCachePath={TILE_CACHE_DIR}
          maximumZ={19}
          flipY={false}
          zIndex={1}
          tileSize={256}
        />

        {/* Faint full route behind */}
        <Polyline
          coordinates={DEMO_STEPS[TOTAL - 1].routePolyline.map(p => ({
            latitude: p.lat,
            longitude: p.lon,
          }))}
          strokeColor="rgba(26,115,232,0.25)"
          strokeWidth={4}
          zIndex={2}
        />

        {/* Travelled portion */}
        <Polyline
          coordinates={polyCoords}
          strokeColor="#1a73e8"
          strokeWidth={5}
          zIndex={3}
        />

        {/* Origin */}
        <Marker
          coordinate={{latitude: DEMO_ORIGIN.lat, longitude: DEMO_ORIGIN.lon}}
          title="Start — DLF CyberHub"
          pinColor="green"
          zIndex={4}
        />

        {/* Destination */}
        <Marker
          coordinate={{latitude: DEMO_DEST.lat, longitude: DEMO_DEST.lon}}
          title="End — IGI T3 Metro"
          pinColor="red"
          zIndex={4}
        />

        {/* Rider position */}
        <Marker
          coordinate={{latitude: currentPos.lat, longitude: currentPos.lon}}
          title="Rider"
          anchor={{x: 0.5, y: 0.5}}
          zIndex={10}>
          <View style={styles.riderDotOuter}>
            <View
              style={[
                styles.riderDotInner,
                {backgroundColor: POS_COLOR[step.positionMode]},
              ]}
            />
          </View>
        </Marker>
      </MapView>

      {/* Crash overlay */}
      {isCrash && (
        <View style={styles.crashBanner}>
          <Text style={styles.crashText}>🚨 CRASH DETECTED — SOS SENT</Text>
        </View>
      )}

      {/* Off-route banner */}
      {step.offRoute && !isCrash && (
        <View style={styles.offRouteBanner}>
          <Text style={styles.offRouteText}>⚠ OFF ROUTE — Recalculating…</Text>
        </View>
      )}

      {/* Top instruction bar */}
      <View style={[styles.instructionBar, {paddingTop: insets.top + 6}]}>
        {/* Mode badges row */}
        <View style={styles.badgeRow}>
          <View style={[styles.badge, {backgroundColor: MODE_COLOR[step.navMode]}]}>
            <Text style={styles.badgeText}>{step.navMode}</Text>
          </View>
          <View style={[styles.badge, {backgroundColor: POS_COLOR[step.positionMode]}]}>
            <Text style={styles.badgeText}>{step.positionMode}</Text>
          </View>
          <Text style={styles.stepCounter}>
            Step {step.activeStepIndex + 1} / {TOTAL}
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
                backgroundColor: step.confidence > 0.6 ? '#34a853' : step.confidence > 0.35 ? '#fbbc04' : '#ea4335',
              },
            ]}
          />
        </View>
        <Text style={styles.confLabel}>
          Confidence {Math.round(step.confidence * 100)}%
        </Text>
      </View>

      {/* Recenter button */}
      <Pressable style={styles.recenterButton} onPress={handleRecenter}>
        <Text style={styles.recenterText}>{'\u2316'}</Text>
      </Pressable>

      {/* Playback controls + stop */}
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 12}]}>
        {/* Step progress bar */}
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
            onPress={handlePrev}
            disabled={stepIdx === 0}>
            <Text style={[styles.ctrlText, stepIdx === 0 && styles.ctrlDisabled]}>
              {'‹ Prev'}
            </Text>
          </Pressable>

          <Pressable
            style={({pressed}) => [styles.playPauseBtn, pressed && styles.playPauseBtnPressed]}
            onPress={() => setPlaying(p => !p)}>
            <Text style={styles.playPauseText}>{playing ? '⏸' : '▶'}</Text>
          </Pressable>

          <Pressable
            style={({pressed}) => [styles.ctrlBtn, pressed && styles.ctrlBtnPressed]}
            onPress={handleNext}
            disabled={stepIdx === TOTAL - 1}>
            <Text style={[styles.ctrlText, stepIdx === TOTAL - 1 && styles.ctrlDisabled]}>
              {'Next ›'}
            </Text>
          </Pressable>
        </View>

        <Pressable
          style={({pressed}) => [styles.stopButton, pressed && styles.stopButtonPressed]}
          onPress={onStop}>
          <Text style={styles.stopButtonText}>Stop Demo</Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#000'},

  crashBanner: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    backgroundColor: '#ea4335',
    padding: 10,
    alignItems: 'center',
    zIndex: 30,
  },
  crashText: {color: '#fff', fontWeight: '900', fontSize: 15, letterSpacing: 0.5},

  offRouteBanner: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    backgroundColor: '#f9a825',
    padding: 8,
    alignItems: 'center',
    zIndex: 30,
  },
  offRouteText: {color: '#4a3000', fontWeight: '800', fontSize: 13},

  instructionBar: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
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
  badge: {
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  badgeText: {color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.5},
  stepCounter: {marginLeft: 'auto', fontSize: 11, color: '#888'},
  instructionText: {fontSize: 17, fontWeight: '700', color: '#1a1a1a', marginBottom: 4},
  distanceText: {fontSize: 13, color: '#555', marginBottom: 6},
  confBarBg: {height: 4, backgroundColor: '#e0e0e0', borderRadius: 2, overflow: 'hidden', marginBottom: 2},
  confBarFill: {height: 4, borderRadius: 2},
  confLabel: {fontSize: 10, color: '#888'},

  riderDotOuter: {
    width: 24, height: 24, borderRadius: 12,
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderWidth: 2, borderColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
    elevation: 4,
  },
  riderDotInner: {width: 14, height: 14, borderRadius: 7},

  recenterButton: {
    position: 'absolute',
    right: 16,
    bottom: 160,
    width: 46, height: 46,
    borderRadius: 23,
    backgroundColor: '#fff',
    alignItems: 'center', justifyContent: 'center',
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.2,
    shadowRadius: 4,
  },
  recenterText: {fontSize: 22, color: '#1a73e8'},

  bottomPanel: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
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
  ctrlBtn: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  ctrlBtnPressed: {opacity: 0.6},
  ctrlText: {fontSize: 15, color: '#1a73e8', fontWeight: '600'},
  ctrlDisabled: {color: '#ccc'},
  playPauseBtn: {
    width: 52, height: 52,
    borderRadius: 26,
    backgroundColor: '#1a73e8',
    alignItems: 'center', justifyContent: 'center',
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
