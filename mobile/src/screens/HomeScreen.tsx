/**
 * HomeScreen
 *
 * Lets the rider enter source and destination, then sends START_NAVIGATION
 * to the NCS (which geocodes via Nominatim and fetches the route from OSRM).
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
import {startNavigation} from '../services/NCSService';
import {UIStateMessage} from '../types';

interface Props {
  onNavigationStarted: (sessionId: string, initialState: UIStateMessage | null) => void;
}

function makeSessionId(): string {
  return `ride_${Date.now()}`;
}

const HomeScreen: React.FC<Props> = ({onNavigationStarted}) => {
  const insets = useSafeAreaInsets();
  const [origin, setOrigin]           = useState('VNIT Nagpur');
  const [destination, setDestination] = useState('Nagpur Airport');
  const [loading, setLoading]         = useState(false);
  const [statusText, setStatusText]   = useState('');

  const handleStart = async () => {
    if (!origin.trim() || !destination.trim()) {
      Alert.alert('Missing fields', 'Please enter both source and destination.');
      return;
    }

    setLoading(true);
    setStatusText('Geocoding locations…');

    const sessionId = makeSessionId();
    try {
      setStatusText('Fetching route from OSRM…');
      const response = await startNavigation(sessionId, origin.trim(), destination.trim());

      if (!response.accepted) {
        Alert.alert(
          'Route unavailable',
          response.reason === 'route_data_required'
            ? 'Could not fetch route. Check internet connection and try again.'
            : `NCS error: ${response.reason}`,
        );
        return;
      }

      // Hand off to the navigation screen
      onNavigationStarted(sessionId, response.ui_state);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      Alert.alert(
        'Connection error',
        `Could not reach NCS.\n\n${msg}\n\nMake sure the NCS server is running on port 8000.`,
      );
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

        {/* Header */}
        <Text style={styles.title}>Smart Helmet</Text>
        <Text style={styles.subtitle}>Offline Navigation</Text>

        {/* Route inputs */}
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

        {/* Info box */}
        <View style={styles.infoBox}>
          <Text style={styles.infoText}>
            {'↳ Route is fetched from OSRM (OpenStreetMap)\n'}
            {'↳ NCS geocodes locations via Nominatim\n'}
            {'↳ Map tiles stream from OSM tile server'}
          </Text>
        </View>

        {/* Status text while loading */}
        {loading && (
          <View style={styles.statusRow}>
            <ActivityIndicator color="#1a73e8" />
            <Text style={styles.statusText}>{statusText}</Text>
          </View>
        )}

        {/* Start button */}
        <Pressable
          style={({pressed}) => [
            styles.startButton,
            pressed && styles.startButtonPressed,
            loading && styles.startButtonDisabled,
          ]}
          onPress={handleStart}
          disabled={loading}>
          <Text style={styles.startButtonText}>
            {loading ? 'Loading route…' : '▶  Start Navigation'}
          </Text>
        </Pressable>

        <Text style={styles.hint}>
          NCS must be running on port 8000.{'\n'}
          Emulator: 10.0.2.2 · Physical device: your LAN IP
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
};

const styles = StyleSheet.create({
  flex: {flex: 1, backgroundColor: '#f8f9fa'},

  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
  },

  title: {
    fontSize: 32,
    fontWeight: '800',
    color: '#1a1a1a',
  },
  subtitle: {
    fontSize: 15,
    color: '#666',
    marginTop: 4,
    marginBottom: 28,
  },

  // Input card
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
  input: {
    fontSize: 16,
    color: '#1a1a1a',
    paddingVertical: 8,
  },
  divider: {
    height: 1,
    backgroundColor: '#f0f0f0',
    marginVertical: 8,
  },

  // Info
  infoBox: {
    backgroundColor: '#e8f4fd',
    borderRadius: 10,
    padding: 12,
    marginBottom: 20,
  },
  infoText: {
    fontSize: 12,
    color: '#1a5276',
    lineHeight: 20,
  },

  // Loading status
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 12,
  },
  statusText: {
    fontSize: 13,
    color: '#555',
  },

  // Start button
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
  startButtonPressed: {
    backgroundColor: '#1558b0',
    transform: [{scale: 0.98}],
  },
  startButtonDisabled: {
    backgroundColor: '#9dbfef',
    elevation: 0,
  },
  startButtonText: {
    color: '#fff',
    fontSize: 17,
    fontWeight: '700',
    letterSpacing: 0.3,
  },

  hint: {
    textAlign: 'center',
    fontSize: 11,
    color: '#aaa',
    lineHeight: 17,
  },
});

export default HomeScreen;
