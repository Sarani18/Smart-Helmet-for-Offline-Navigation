/**
 * DemoHomeScreen
 *
 * Shows a coordinate-based route preview (pure React Native, no native map)
 * and a "Start Demo Trip" button.  No GPS, no network, no Google Maps SDK needed
 * — all data is baked in from demoRoute.ts.
 */

import React, {useMemo} from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {
  DEMO_ORIGIN,
  DEMO_DEST,
  FULL_POLYLINE,
  DEMO_STEPS,
} from './demoRoute';
import type {LatLon} from './demoRoute';

interface Props {
  onStart: () => void;
  onBack: () => void;
}

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
    // latitude increases upward on map, y increases downward on screen
    y: pad + ((maxLat - p.lat) / (maxLat - minLat)) * rangeH,
  });
}

// ── Route mini-map (pure React Native Views, no native map) ──────────────────

interface MiniMapProps {
  width: number;
  height: number;
}

const RouteMiniMap: React.FC<MiniMapProps> = ({width, height}) => {
  const scaler = useMemo(
    () => buildScaler(FULL_POLYLINE, width, height, 18),
    [width, height],
  );
  // Sample every 3rd point for performance (~124 dots)
  const routeDots = useMemo(
    () => FULL_POLYLINE.filter((_, i) => i % 3 === 0),
    [],
  );
  const originPx = scaler(DEMO_ORIGIN);
  const destPx = scaler(DEMO_DEST);

  return (
    <View style={[styles.miniMap, {width, height}]}>
      {routeDots.map((p, i) => {
        const {x, y} = scaler(p);
        return (
          <View key={i} style={[styles.routeDot, {left: x - 2, top: y - 2}]} />
        );
      })}
      <View
        style={[styles.marker, styles.markerOrigin, {left: originPx.x - 7, top: originPx.y - 7}]}
      />
      <View
        style={[styles.marker, styles.markerDest, {left: destPx.x - 7, top: destPx.y - 7}]}
      />
      <Text style={[styles.mapLabel, {left: originPx.x + 10, top: originPx.y - 8}]}>
        Start
      </Text>
      <Text style={[styles.mapLabel, {left: destPx.x + 10, top: destPx.y - 8}]}>
        IGI T3
      </Text>
    </View>
  );
};

// ── Screen ────────────────────────────────────────────────────────────────────

const DemoHomeScreen: React.FC<Props> = ({onStart, onBack}) => {
  const insets = useSafeAreaInsets();
  const {width} = useWindowDimensions();

  return (
    <ScrollView
      style={styles.bg}
      contentContainerStyle={[
        styles.container,
        {paddingTop: insets.top + 16, paddingBottom: insets.bottom + 24},
      ]}
      showsVerticalScrollIndicator={false}>

      {/* Header */}
      <View style={styles.headerRow}>
        <Pressable onPress={onBack} style={styles.backBtn} hitSlop={12}>
          <Text style={styles.backBtnText}>{'‹ Back'}</Text>
        </Pressable>
        <Text style={styles.screenTitle}>Demo Mode</Text>
        <View style={styles.backBtn} />
      </View>

      {/* Route card with mini-map */}
      <View style={styles.card}>
        <Text style={styles.routeTitle}>DLF CyberHub → IGI Airport T3</Text>
        <Text style={styles.routeMeta}>
          NH-48 Delhi-Gurgaon Expressway · ~10.9 km · {DEMO_STEPS.length} steps
        </Text>
        <View style={styles.miniMapWrapper}>
          <RouteMiniMap width={width - 64} height={220} />
        </View>
        <View style={styles.endpointRow}>
          <View style={[styles.endpointChip, styles.originChip]}>
            <Text style={styles.endpointLabel}>FROM</Text>
            <Text style={styles.endpointText}>DLF CyberHub</Text>
          </View>
          <Text style={styles.arrow}>{'→'}</Text>
          <View style={[styles.endpointChip, styles.destChip]}>
            <Text style={styles.endpointLabel}>TO</Text>
            <Text style={styles.endpointText}>IGI T3 Metro</Text>
          </View>
        </View>
      </View>

      {/* Mode legend */}
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>Sensor modes simulated</Text>
        {[
          {color: '#34a853', label: 'ONLINE + GPS', desc: 'Full connectivity, precise position'},
          {color: '#fbbc04', label: 'OFFLINE / VISUAL', desc: 'No network — CV localization active'},
          {color: '#ea4335', label: 'DEGRADED / UNKNOWN', desc: 'Signal lost, last known position held'},
        ].map(item => (
          <View key={item.label} style={styles.legendRow}>
            <View style={[styles.legendDot, {backgroundColor: item.color}]} />
            <View style={styles.legendTextCol}>
              <Text style={styles.legendLabel}>{item.label}</Text>
              <Text style={styles.legendDesc}>{item.desc}</Text>
            </View>
          </View>
        ))}
      </View>

      <View style={styles.infoBox}>
        <Text style={styles.infoText}>
          {'Simulates: GPS → VISUAL → DEGRADED → UNKNOWN → CRASH alert → OFF ROUTE → ARRIVED\n'}
          {'No GPS, no network, no permissions required.'}
        </Text>
      </View>

      <Pressable
        style={({pressed}) => [
          styles.startButton,
          pressed && styles.startButtonPressed,
        ]}
        onPress={onStart}>
        <Text style={styles.startButtonText}>{'▶  Start Demo Trip'}</Text>
      </Pressable>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  bg: {flex: 1, backgroundColor: '#f0f4f8'},
  container: {paddingHorizontal: 20},

  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 20,
  },
  backBtn: {width: 60},
  backBtnText: {fontSize: 16, color: '#1a73e8', fontWeight: '600'},
  screenTitle: {fontSize: 17, fontWeight: '800', color: '#1a1a1a'},

  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 16,
    marginBottom: 14,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 1},
    shadowOpacity: 0.08,
    shadowRadius: 6,
  },
  routeTitle: {fontSize: 16, fontWeight: '800', color: '#1a1a1a', marginBottom: 4},
  routeMeta: {fontSize: 12, color: '#666', marginBottom: 14},

  miniMapWrapper: {borderRadius: 10, overflow: 'hidden', marginBottom: 14},
  miniMap: {backgroundColor: '#0d1b2a', position: 'relative'},
  routeDot: {
    position: 'absolute',
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: 'rgba(26,115,232,0.65)',
  },
  marker: {
    position: 'absolute',
    width: 14,
    height: 14,
    borderRadius: 7,
    borderWidth: 2,
    borderColor: '#fff',
  },
  markerOrigin: {backgroundColor: '#34a853'},
  markerDest: {backgroundColor: '#ea4335'},
  mapLabel: {
    position: 'absolute',
    fontSize: 9,
    color: 'rgba(255,255,255,0.75)',
    fontWeight: '700',
  },

  endpointRow: {flexDirection: 'row', alignItems: 'center', gap: 8},
  endpointChip: {flex: 1, borderRadius: 10, padding: 10},
  originChip: {backgroundColor: '#e8f5e9'},
  destChip: {backgroundColor: '#fce8e6'},
  endpointLabel: {
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 1,
    color: '#666',
    marginBottom: 2,
  },
  endpointText: {fontSize: 13, fontWeight: '700', color: '#1a1a1a'},
  arrow: {fontSize: 18, color: '#aaa'},

  sectionTitle: {fontSize: 13, fontWeight: '700', color: '#333', marginBottom: 10},
  legendRow: {flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginBottom: 10},
  legendDot: {width: 10, height: 10, borderRadius: 5, marginTop: 3},
  legendTextCol: {flex: 1},
  legendLabel: {fontSize: 12, fontWeight: '700', color: '#1a1a1a'},
  legendDesc: {fontSize: 11, color: '#666', marginTop: 1},

  infoBox: {
    backgroundColor: '#e8f4fd',
    borderRadius: 12,
    padding: 14,
    marginBottom: 20,
  },
  infoText: {fontSize: 12, color: '#1a5276', lineHeight: 20},

  startButton: {
    backgroundColor: '#1a73e8',
    borderRadius: 14,
    paddingVertical: 18,
    alignItems: 'center',
    elevation: 5,
    shadowColor: '#1a73e8',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  startButtonPressed: {backgroundColor: '#1558b0', transform: [{scale: 0.98}]},
  startButtonText: {color: '#fff', fontSize: 17, fontWeight: '700', letterSpacing: 0.3},
});

export default DemoHomeScreen;
