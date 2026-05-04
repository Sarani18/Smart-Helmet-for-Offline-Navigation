/**
 * HomeScreen
 *
 * Flow on "Start Navigation":
 *   1. Request Android permissions
 *   2. Check route cache (same origin+dest → skip all network, navigate instantly)
 *   3. Geocode via Nominatim (15s timeout)
 *   4. Fetch route via OSRM (15s timeout, cached to disk)
 *   5. Navigate immediately — tile download runs in background
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
import Geolocation from '@react-native-community/geolocation';
import {useSafeAreaInsets} from 'react-native-safe-area-context';
import {requestApplicationPermissions} from '../utils/permissions';
import {
  geocode,
  fetchRoute,
  makeRouteCacheKey,
  loadCachedRoute,
} from '../services/routeService';
import {downloadTilesForRoute} from '../services/tileService';
import {startGPS} from '../services/gpsService';
import type {ParsedRoute, LatLon} from '../services/routeService';

interface Props {
  onNavigationStarted: (
    sessionId: string,
    route: ParsedRoute,
    origin: LatLon,
    dest: LatLon,
  ) => void;
  onDemo: () => void;
}

function makeSessionId(): string {
  return `ride_${Date.now()}`;
}

const HomeScreen: React.FC<Props> = ({onNavigationStarted, onDemo}) => {
  const insets = useSafeAreaInsets();
  const [origin, setOrigin] = useState('Pune Airport');
  const [destination, setDestination] = useState('MIT World Peace University, Pune');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  // When user taps "My Location", we store the raw coords to skip geocoding
  const [originCoords, setOriginCoords] = useState<LatLon | null>(null);
  const [fetchingLoc, setFetchingLoc] = useState(false);

  const handleUseMyLocation = async () => {
    setFetchingLoc(true);
    setOrigin('Fetching GPS…');
    setOriginCoords(null);

    // Ensure location permission is granted before calling GPS API
    const perms = await requestApplicationPermissions();
    if (!perms.fineLocation) {
      setOrigin('VNIT Nagpur');
      setOriginCoords(null);
      setFetchingLoc(false);
      Alert.alert(
        'Location permission required',
        'Grant "Fine location" permission to use your current location as the start point.',
      );
      return;
    }

    Geolocation.getCurrentPosition(
      pos => {
        const coords: LatLon = {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
        };
        setOriginCoords(coords);
        // Show rounded coords as a readable label
        const label = `${coords.lat.toFixed(5)}, ${coords.lon.toFixed(5)}`;
        setOrigin(label);
        setFetchingLoc(false);
      },
      err => {
        console.warn('getCurrentPosition failed:', err.code, err.message);
        setOrigin('VNIT Nagpur'); // revert to default
        setOriginCoords(null);
        setFetchingLoc(false);
        Alert.alert(
          'Location unavailable',
          `Could not get your GPS position (${err.message}).\n\nMake sure GPS is enabled and you have location permission.`,
        );
      },
      {
        enableHighAccuracy: true,
        timeout: 60000, // 60s — try hard to get a fix
        maximumAge: 10000,
      },
    );
  };

  const handleStart = async () => {
    if (!origin.trim() || !destination.trim()) {
      Alert.alert('Missing fields', 'Please enter both source and destination.');
      return;
    }

    setLoading(true);
    setStatusText('Checking permissions…');

    try {
      // Step 1: Permissions
      const perms = await requestApplicationPermissions();
      if (!perms.allCriticalGranted) {
        Alert.alert(
          'Location required',
          'Fine location permission is needed for navigation.',
        );
        return;
      }

      // Warm up GPS while route is being fetched — reduces cold-start delay on NavigationScreen
      startGPS();

      const sessionId = makeSessionId();
      const cacheKey = makeRouteCacheKey(origin.trim(), destination.trim());

      // Step 2: Try cache first — no network needed
      setStatusText('Checking local cache…');
      const cached = await loadCachedRoute(cacheKey);
      if (cached) {
        // Need coordinates for the map markers — geocode quickly (or use route endpoints)
        const firstPt = cached.polyline[0];
        const lastPt = cached.polyline[cached.polyline.length - 1];
        // Kick off background tile download (non-blocking)
        downloadTilesForRoute(cached.polyline, [14, 15]).catch(e =>
          console.warn('Background tile download failed:', e),
        );
        onNavigationStarted(sessionId, {...cached, id: sessionId}, firstPt, lastPt);
        return;
      }

      // Step 3: Geocode (only destination if current-location was used for origin)
      setStatusText('Geocoding locations…');
      let resolvedOrigin: LatLon;
      if (originCoords) {
        resolvedOrigin = originCoords; // already have GPS coords — skip geocoding
      } else {
        resolvedOrigin = await geocode(origin.trim());
      }
      const destCoords = await geocode(destination.trim());

      // Step 4: Fetch route from OSRM
      setStatusText('Fetching route from OSRM… (may take up to 2 min)');
      const route = await fetchRoute(resolvedOrigin, destCoords, sessionId, cacheKey);

      // Step 5: Navigate immediately — tiles download in background
      setStatusText('Starting navigation…');
      downloadTilesForRoute(route.polyline, [14, 15]).catch(e =>
        console.warn('Background tile download failed:', e),
      );
      onNavigationStarted(sessionId, route, resolvedOrigin, destCoords);

    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      Alert.alert('Could not start navigation', msg);
    } finally {
      setLoading(false);
      setStatusText('');
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
          <View style={styles.inputRow}>
            <TextInput
              style={[styles.input, styles.inputFlex]}
              value={origin}
              onChangeText={text => {
                setOrigin(text);
                setOriginCoords(null); // clear saved coords when user types
              }}
              placeholder="e.g. VNIT Nagpur"
              placeholderTextColor="#aaa"
              returnKeyType="next"
              editable={!loading && !fetchingLoc}
            />
            <Pressable
              style={({pressed}) => [
                styles.locButton,
                pressed && styles.locButtonPressed,
                (loading || fetchingLoc) && styles.locButtonDisabled,
              ]}
              onPress={handleUseMyLocation}
              disabled={loading || fetchingLoc}>
              {fetchingLoc ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.locButtonText}>{'\u25CE'} Me</Text>
              )}
            </Pressable>
          </View>
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
            {'↳ Route cached after first fetch — retries are instant\n'}
            {'↳ Map tiles download in background after navigation starts\n'}
            {'↳ Works fully offline once route is cached'}
          </Text>
        </View>

        {loading && (
          <View style={styles.statusRow}>
            <ActivityIndicator color="#1a73e8" />
            <Text style={styles.statusText}>{statusText}</Text>
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
            {loading ? 'Loading…' : '▶  Start Navigation'}
          </Text>
        </Pressable>

        <Pressable
          style={({pressed}) => [
            styles.demoButton,
            pressed && styles.demoButtonPressed,
            loading && styles.startButtonDisabled,
          ]}
          onPress={onDemo}
          disabled={loading}>
          <Text style={styles.demoButtonText}>
            {'⬡  Demo Mode (CyberHub → IGI)'}
          </Text>
        </Pressable>

        <Text style={styles.hint}>
          First use requires internet for route + tiles.{'\n'}
          Same route loads instantly on retry.
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
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  statusText: {fontSize: 13, color: '#555', flex: 1},
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
  demoButton: {
    backgroundColor: '#fff',
    borderRadius: 14,
    paddingVertical: 15,
    alignItems: 'center',
    marginBottom: 12,
    borderWidth: 1.5,
    borderColor: '#1a73e8',
  },
  demoButtonPressed: {backgroundColor: '#e8f0fe', transform: [{scale: 0.98}]},
  demoButtonText: {color: '#1a73e8', fontSize: 15, fontWeight: '700'},
  hint: {textAlign: 'center', fontSize: 11, color: '#aaa', lineHeight: 17},
  inputRow: {flexDirection: 'row', alignItems: 'center', gap: 8},
  inputFlex: {flex: 1},
  locButton: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 52,
  },
  locButtonPressed: {backgroundColor: '#1558b0'},
  locButtonDisabled: {backgroundColor: '#9dbfef'},
  locButtonText: {color: '#fff', fontSize: 12, fontWeight: '700'},
});

export default HomeScreen;
