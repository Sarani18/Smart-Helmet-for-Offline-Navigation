/**
 * DemoHomeScreen
 *
 * Shows the NH-48 route on a MapLibre GL map (OSM tiles, same as embedded web UI)
 * and a "Start Demo Trip" button.  No Google Maps SDK needed.
 */

import React, {useRef} from 'react';
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
import MapLibreView from '../components/MapLibreView';
import type {MapLibreViewRef} from '../components/MapLibreView';

interface Props {
  onStart: () => void;
  onBack: () => void;
}

// Midpoint of the route for initial map center
const CENTER_LON = (DEMO_ORIGIN.lon + DEMO_DEST.lon) / 2;
const CENTER_LAT = (DEMO_ORIGIN.lat + DEMO_DEST.lat) / 2;

// Pre-build [lon, lat] pairs once (MapLibre uses lon, lat order)
const ROUTE_COORDS: [number, number][] = FULL_POLYLINE.map(p => [p.lon, p.lat]);

const DemoHomeScreen: React.FC<Props> = ({onStart, onBack}) => {
  const insets = useSafeAreaInsets();
  const {width} = useWindowDimensions();
  const mapRef = useRef<MapLibreViewRef>(null);

  const handleMapReady = () => {
    // Draw the full route polyline on the map
    mapRef.current?.send({type: 'setRoute', coords: ROUTE_COORDS});
    // Place origin marker
    mapRef.current?.send({
      type: 'setRider',
      lon: DEMO_ORIGIN.lon,
      lat: DEMO_ORIGIN.lat,
      color: '#34a853',
    });
  };

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

      {/* Route card with MapLibre map */}
      <View style={styles.card}>
        <Text style={styles.routeTitle}>DLF CyberHub → IGI Airport T3</Text>
        <Text style={styles.routeMeta}>
          NH-48 Delhi-Gurgaon Expressway · ~10.9 km · {DEMO_STEPS.length} steps
        </Text>
        <View style={[styles.mapWrapper, {width: width - 64}]}>
          <MapLibreView
            ref={mapRef}
            style={styles.map}
            initialLon={CENTER_LON}
            initialLat={CENTER_LAT}
            initialZoom={11}
            onReady={handleMapReady}
          />
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
          {'No GPS or permissions required.'}
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

  mapWrapper: {height: 220, borderRadius: 10, overflow: 'hidden', marginBottom: 14},
  map: {flex: 1},

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
