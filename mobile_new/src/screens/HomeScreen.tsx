/**
 * HomeScreen
 *
 * Rider enters origin and destination. On "Start Navigation":
 *   1. Request Android permissions (location, BLE)
 *   2. Geocode via Nominatim
 *   3. Fetch route via OSRM and cache to disk
 *   4. Download OSM tiles for the route bounding box (with progress)
 *   5. Hand off to NavigationScreen
 *
 * No external server required — all logic runs on-device.
 */

import React, {useState} from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {requestApplicationPermissions} from '../utils/permissions';
import {geocode, fetchRoute} from '../services/routeService';
import {downloadTilesForRoute} from '../services/tileService';
import type {ParsedRoute, LatLon} from '../services/routeService';

interface Props {
  onNavigationStarted: (
    sessionId: string,
    route: ParsedRoute,
    origin: LatLon,
    dest: LatLon,
  ) => void;
}

function makeSessionId(): string {
  // Hardcoded for testing with the Python scripts
  return 'test_mobile_session'; 
}

const HomeScreen: React.FC<Props> = ({onNavigationStarted}) => {
  const insets = useSafeAreaInsets();
  const [origin, setOrigin] = useState('VNIT Nagpur');
  const [destination, setDestination] = useState('Nagpur Airport');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [tileProgress, setTileProgress] = useState<{d: number; t: number} | null>(null);

  const handleStart = async () => {
    if (!origin.trim() || !destination.trim()) {
      Alert.alert('Missing fields', 'Please enter both source and destination.');
      return;
    }

    setLoading(true);
    setTileProgress(null);

    try {
      // Step 1: Permissions
      setStatusText('Requesting permissions…');
      const perms = await requestApplicationPermissions();
      if (!perms.allCriticalGranted) {
        Alert.alert(
          'Location required',
          'Fine location permission is needed for navigation.',
        );
        return;
      }

      // Step 2: Geocode
      setStatusText('Geocoding locations…');
      const [originCoords, destCoords] = await Promise.all([
        geocode(origin.trim()),
        geocode(destination.trim()),
      ]);

      // Step 3: Fetch route from OSRM and cache
      setStatusText('Fetching route from OSRM…');
      const sessionId = makeSessionId();
      const route = await fetchRoute(originCoords, destCoords, sessionId);

      // Step 4: Download tiles for the route bounding box
      setStatusText('Downloading offline map tiles…');
      await downloadTilesForRoute(route.polyline, [14, 15], p => {
        setTileProgress({d: p.downloaded, t: p.total});
      });

      // Step 5: Hand off
      onNavigationStarted(sessionId, route, originCoords, destCoords);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
      setStatusText('');
      setTileProgress(null);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.flex}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView
        contentContainerStyle={[
          styles.container,
          {paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24},
        ]}
        keyboardShouldPersistTaps="handled">

        <Text style={styles.title}>Smart Helmet</Text>
        <Text style={styles.subtitle}>Standalone Offline Navigation</Text>

        <View style={styles.card}>
          <Text style={styles.inputLabel}>FROM</Text>
          <TextInput
            style={styles.input}
            value={origin}
            onChangeText={setOrigin}
            placeholder="e.g. VNIT Nagpur"
            placeholderTextColor="#aaa"
            returnKeyType="next"
            editable={!loading}
          />
          <View style={styles.divider} />
          <Text style={styles.inputLabel}>TO</Text>
          <TextInput
            style={styles.input}
            value={destination}
            onChangeText={setDestination}
            placeholder="e.g. Nagpur Airport"
            placeholderTextColor="#aaa"
            returnKeyType="done"
            onSubmitEditing={handleStart}
            editable={!loading}
          />
        </View>

        <View style={styles.infoBox}>
          <Text style={styles.infoText}>
            {'↳ Route fetched from OSRM (on first use)\n'}
            {'↳ Map tiles downloaded and cached offline\n'}
            {'↳ Navigation runs fully on-device — no server needed'}
          </Text>
        </View>

        {loading && (
          <View style={styles.statusRow}>
            <ActivityIndicator color="#1a73e8" />
            <View style={styles.statusTextCol}>
              <Text style={styles.statusText}>{statusText}</Text>
              {tileProgress && (
                <Text style={styles.tileText}>
                  Tiles: {tileProgress.d} / {tileProgress.t}
                </Text>
              )}
            </View>
          </View>
        )}

        <Pressable
          style={({pressed}) => [
            styles.startButton,
            pressed && styles.startButtonPressed,
            loading && styles.startButtonDisabled,
          ]}
          onPress={handleStart}
          disabled={loading}>
          <Text style={styles.startButtonText}>
            {loading ? 'Setting up…' : '▶  Start Navigation'}
          </Text>
        </Pressable>

        <Text style={styles.hint}>
          Requires internet on first use to download route + tiles.{'\n'}
          After that, works fully offline.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  flex: {flex: 1, backgroundColor: '#f8f9fa'},
  container: {flexGrow: 1, paddingHorizontal: 24},
  title: {fontSize: 32, fontWeight: '800', color: '#1a1a1a'},
  subtitle: {fontSize: 15, color: '#666', marginTop: 4, marginBottom: 28},
  card: {
    backgroundColor: '#fff',
    borderRadius: 16,
    paddingHorizontal: 16,
    paddingVertical: 12,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: {width: 0, height: 2},
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
  inputLabel: {
    fontSize: 10,
    fontWeight: '700',
    color: '#888',
    letterSpacing: 1.2,
    marginBottom: 4,
    marginTop: 4,
    textTransform: 'uppercase',
  },
  input: {fontSize: 16, color: '#1a1a1a', paddingVertical: 8},
  divider: {height: 1, backgroundColor: '#f0f0f0', marginVertical: 8},
  infoBox: {
    backgroundColor: '#e8f4fd',
    borderRadius: 10,
    padding: 12,
    marginBottom: 20,
  },
  infoText: {fontSize: 12, color: '#1a5276', lineHeight: 20},
  statusRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    marginBottom: 12,
  },
  statusTextCol: {flexDirection: 'column'},
  statusText: {fontSize: 13, color: '#555'},
  tileText: {fontSize: 11, color: '#888', marginTop: 2},
  startButton: {
    backgroundColor: '#1a73e8',
    borderRadius: 14,
    paddingVertical: 18,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#1a73e8',
    shadowOffset: {width: 0, height: 4},
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  startButtonPressed: {backgroundColor: '#1558b0', transform: [{scale: 0.98}]},
  startButtonDisabled: {backgroundColor: '#9dbfef', elevation: 0},
  startButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
    letterSpacing: 0.3,
  },
  hint: {textAlign: 'center', fontSize: 11, color: '#aaa', lineHeight: 17},
});

export default HomeScreen;
