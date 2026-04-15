/**
 * DemoHomeScreen
 *
 * Shows the full NH-48 route on a map (DLF CyberHub → IGI T3 Metro)
 * with a "Start Demo Trip" button. No GPS, no network needed — all
 * coordinates are baked in from demoRoute.ts (ported from test_input.py).
 */

import React from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import MapView, {Marker, Polyline, UrlTile} from 'react-native-maps';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {
  DEMO_ORIGIN,
  DEMO_DEST,
  FULL_POLYLINE,
  DEMO_STEPS,
} from './demoRoute';
import {TILE_CACHE_DIR} from '../services/tileService';

interface Props {
  onStart: () => void;
  onBack: () => void;
}

const DemoHomeScreen: React.FC<Props> = ({onStart, onBack}) => {
  const insets = useSafeAreaInsets();

  const polyCoords = FULL_POLYLINE.map(p => ({
    latitude: p.lat,
    longitude: p.lon,
  }));

  // Bounding region that fits the whole route
  const initialRegion = {
    latitude: (DEMO_ORIGIN.lat + DEMO_DEST.lat) / 2,
    longitude: (DEMO_ORIGIN.lon + DEMO_DEST.lon) / 2,
    latitudeDelta: Math.abs(DEMO_DEST.lat - DEMO_ORIGIN.lat) * 1.4,
    longitudeDelta: Math.abs(DEMO_DEST.lon - DEMO_ORIGIN.lon) * 1.4,
  };

  return (
    <View style={styles.container}>
      {/* Map — full screen behind everything */}
      <MapView
        style={StyleSheet.absoluteFillObject}
        mapType="none"
        provider={undefined}
        rotateEnabled={false}
        initialRegion={initialRegion}>
        <UrlTile
          urlTemplate="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          tileCachePath={TILE_CACHE_DIR}
          maximumZ={19}
          flipY={false}
          zIndex={1}
          tileSize={256}
        />
        <Polyline
          coordinates={polyCoords}
          strokeColor="#1a73e8"
          strokeWidth={4}
          zIndex={2}
        />
        <Marker
          coordinate={{latitude: DEMO_ORIGIN.lat, longitude: DEMO_ORIGIN.lon}}
          title="Start — DLF CyberHub"
          pinColor="green"
          zIndex={3}
        />
        <Marker
          coordinate={{latitude: DEMO_DEST.lat, longitude: DEMO_DEST.lon}}
          title="End — IGI T3 Metro"
          pinColor="red"
          zIndex={3}
        />
      </MapView>

      {/* Top bar */}
      <View style={[styles.topBar, {paddingTop: insets.top + 8}]}>
        <Pressable onPress={onBack} style={styles.backBtn}>
          <Text style={styles.backBtnText}>{'‹ Back'}</Text>
        </Pressable>
        <Text style={styles.topTitle}>Demo Mode</Text>
        <View style={styles.backBtn} /> {/* spacer */}
      </View>

      {/* Bottom panel */}
      <View style={[styles.bottomPanel, {paddingBottom: insets.bottom + 16}]}>
        <Text style={styles.routeTitle}>
          DLF CyberHub → IGI Airport T3 Metro
        </Text>
        <Text style={styles.routeMeta}>
          NH-48 Delhi-Gurgaon Expressway · ~10.9 km · {DEMO_STEPS.length} steps
        </Text>

        {/* Mode legend */}
        <View style={styles.legendRow}>
          {[
            {color: '#34a853', label: 'ONLINE+GPS'},
            {color: '#fbbc04', label: 'OFFLINE/VISUAL'},
            {color: '#ea4335', label: 'DEGRADED'},
          ].map(item => (
            <View key={item.label} style={styles.legendItem}>
              <View style={[styles.legendDot, {backgroundColor: item.color}]} />
              <Text style={styles.legendText}>{item.label}</Text>
            </View>
          ))}
        </View>

        <Text style={styles.demoNote}>
          {'Simulates all sensor modes: GPS → VISUAL → DEGRADED → UNKNOWN → CRASH → ARRIVED'}
        </Text>

        <Pressable
          style={({pressed}) => [
            styles.startButton,
            pressed && styles.startButtonPressed,
          ]}
          onPress={onStart}>
          <Text style={styles.startButtonText}>▶  Start Demo Trip</Text>
        </Pressable>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {flex: 1, backgroundColor: '#000'},

  topBar: {
    position: 'absolute',
    top: 0, left: 0, right: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 10,
    backgroundColor: 'rgba(255,255,255,0.95)',
    elevation: 6,
  },
  backBtn: {width: 60},
  backBtnText: {fontSize: 16, color: '#1a73e8', fontWeight: '600'},
  topTitle: {fontSize: 16, fontWeight: '800', color: '#1a1a1a'},

  bottomPanel: {
    position: 'absolute',
    bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(255,255,255,0.97)',
    paddingHorizontal: 20,
    paddingTop: 16,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    elevation: 12,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: -3},
    shadowOpacity: 0.12,
    shadowRadius: 8,
  },
  routeTitle: {
    fontSize: 17,
    fontWeight: '800',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  routeMeta: {fontSize: 13, color: '#666', marginBottom: 12},
  legendRow: {flexDirection: 'row', gap: 12, marginBottom: 10, flexWrap: 'wrap'},
  legendItem: {flexDirection: 'row', alignItems: 'center', gap: 5},
  legendDot: {width: 8, height: 8, borderRadius: 4},
  legendText: {fontSize: 11, color: '#444'},
  demoNote: {
    fontSize: 11,
    color: '#777',
    lineHeight: 16,
    marginBottom: 14,
    fontStyle: 'italic',
  },
  startButton: {
    backgroundColor: '#1a73e8',
    borderRadius: 14,
    paddingVertical: 17,
    alignItems: 'center',
    elevation: 4,
    shadowColor: '#1a73e8',
    shadowOffset: {width: 0, height: 3},
    shadowOpacity: 0.3,
    shadowRadius: 6,
  },
  startButtonPressed: {backgroundColor: '#1558b0', transform: [{scale: 0.98}]},
  startButtonText: {color: '#fff', fontSize: 17, fontWeight: '700', letterSpacing: 0.3},
});

export default DemoHomeScreen;
