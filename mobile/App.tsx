/**
 * Smart Helmet App — Root
 *
 * Startup flow:
 *   1. PermissionGate — request GPS + BLE runtime permissions (blocks HomeScreen)
 *   2. useGPS starts as a daemon — always watching, never shut down
 *      (GPS runs even on HomeScreen; only pings NCS when a session is active)
 *   3. HomeScreen — origin/destination → START_NAVIGATION → NCS
 *   4. NavigationScreen — live map, polls NCS, receives gpsState as prop
 *
 * GPS is lifted here (not in NavigationScreen) so it begins watching the moment
 * the user grants location permission, exactly like Google Maps.
 *
 * anchorCallbackRef bridges useGPS ↔ useDeadReckoning across the component tree:
 *   - NavigationScreen registers its DR anchor() via onRegisterAnchor
 *   - App forwards each GPS fix to that anchor
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {SafeAreaProvider, useSafeAreaInsets} from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import NavigationScreen from './src/screens/NavigationScreen';
import {usePermissions} from './src/hooks/usePermissions';
import {useGPS, GPSPosition, GPSState} from './src/hooks/useGPS';
import {UIStateMessage} from './src/types';

// ── App-level state ───────────────────────────────────────────────────────────

type AppScreen =
  | {screen: 'home'}
  | {screen: 'navigation'; sessionId: string; initialState: UIStateMessage | null};

// ── Permission gate ───────────────────────────────────────────────────────────

interface PermissionGateProps {children: React.ReactNode}

const PermissionGate: React.FC<PermissionGateProps> = ({children}) => {
  const insets = useSafeAreaInsets();
  const {state, requestAll} = usePermissions();

  useEffect(() => { requestAll(); }, [requestAll]);

  if (state.checking) {
    return (
      <View style={[gate.container, {paddingTop: insets.top + 24}]}>
        <ActivityIndicator size="large" color="#1a73e8" />
        <Text style={gate.title}>Checking permissions…</Text>
      </View>
    );
  }

  if (!state.locationGranted) {
    return (
      <View style={[gate.container, {paddingTop: insets.top + 24}]}>
        <Text style={gate.icon}>📍</Text>
        <Text style={gate.title}>Location required</Text>
        <Text style={gate.body}>
          Smart Helmet needs GPS access to track your ride and navigate offline.
        </Text>
        {state.missing.length > 0 && (
          <View style={gate.missingBox}>
            {state.missing.map(m => (
              <Text key={m} style={gate.missingItem}>• {m}</Text>
            ))}
          </View>
        )}
        <Pressable
          style={({pressed}) => [gate.button, pressed && gate.buttonPressed]}
          onPress={requestAll}>
          <Text style={gate.buttonText}>Grant Permissions</Text>
        </Pressable>
        <Text style={gate.hint}>
          If the dialog does not appear, open{'\n'}
          Settings → Apps → Smart Helmet → Permissions
        </Text>
      </View>
    );
  }

  return <>{children}</>;
};

// ── Root ──────────────────────────────────────────────────────────────────────

function App(): React.JSX.Element {
  const [appScreen, setAppScreen] = useState<AppScreen>({screen: 'home'});

  // Bridge: NavigationScreen registers its DR anchor() here.
  // Each GPS fix in useGPS calls anchorRef.current to keep DR in sync.
  const anchorRef = useRef<((lat: number, lon: number, speed: number) => void) | null>(null);

  const sessionId = appScreen.screen === 'navigation' ? appScreen.sessionId : '';

  // GPS daemon — starts after permission, runs forever
  const gpsState: GPSState = useGPS(sessionId, {
    onGPSFix: useCallback((pos: GPSPosition) => {
      anchorRef.current?.(pos.latitude, pos.longitude, pos.speed);
    }, []),
  });

  const handleRegisterAnchor = useCallback(
    (fn: ((lat: number, lon: number, speed: number) => void) | null) => {
      anchorRef.current = fn;
    }, [],
  );

  return (
    <SafeAreaProvider>
      <PermissionGate>
        {appScreen.screen === 'navigation' ? (
          <NavigationScreen
            sessionId={appScreen.sessionId}
            initialState={appScreen.initialState}
            gpsState={gpsState}
            onRegisterAnchor={handleRegisterAnchor}
            onStop={() => setAppScreen({screen: 'home'})}
          />
        ) : (
          <HomeScreen
            onNavigationStarted={(sessionId, initialState) =>
              setAppScreen({screen: 'navigation', sessionId, initialState})
            }
          />
        )}
      </PermissionGate>
    </SafeAreaProvider>
  );
}

// ── Permission gate styles ────────────────────────────────────────────────────

const gate = StyleSheet.create({
  container: {
    flex: 1, backgroundColor: '#f8f9fa',
    alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: 32,
  },
  icon:  {fontSize: 48, marginBottom: 16},
  title: {fontSize: 22, fontWeight: '800', color: '#1a1a1a', marginBottom: 12, textAlign: 'center'},
  body:  {fontSize: 14, color: '#555', textAlign: 'center', lineHeight: 22, marginBottom: 20},
  missingBox: {
    backgroundColor: '#fff3cd', borderRadius: 10, padding: 12,
    marginBottom: 20, alignSelf: 'stretch',
  },
  missingItem: {fontSize: 13, color: '#856404', marginBottom: 4},
  button: {
    backgroundColor: '#1a73e8', borderRadius: 12,
    paddingVertical: 14, paddingHorizontal: 32, marginBottom: 16,
  },
  buttonPressed: {backgroundColor: '#1558b0'},
  buttonText:    {color: '#fff', fontSize: 16, fontWeight: '700'},
  hint:          {fontSize: 11, color: '#aaa', textAlign: 'center', lineHeight: 17},
});

export default App;
