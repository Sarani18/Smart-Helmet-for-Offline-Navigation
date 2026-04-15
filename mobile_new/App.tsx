/**
 * Smart Helmet Navigation — standalone app root.
 * Routes between HomeScreen (route setup) and NavigationScreen (live nav).
 * Uses react-native-background-actions to keep the BLE + position loop alive
 * when the screen is off.
 */

import React, {useState} from 'react';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import BackgroundService from 'react-native-background-actions';
import HomeScreen from './src/screens/HomeScreen';
import NavigationScreen from './src/screens/NavigationScreen';
import type {ParsedRoute, LatLon} from './src/services/routeService';

type Screen = 'home' | 'navigation';

interface NavSession {
  sessionId: string;
  route: ParsedRoute;
  origin: LatLon;
  dest: LatLon;
}

/**
 * Background task that keeps the JS thread alive under a foreground notification.
 * The actual sensor/BLE work happens in positionCoordinator + bleService —
 * this just prevents Android from killing the process.
 */
const backgroundTask = async (_taskData: unknown) => {
  await new Promise<void>(resolve => {
    BackgroundService.on('expiration', () => {
      resolve();
    });
  });
};

const backgroundOptions = {
  taskName: 'SmartHelmetNav',
  taskTitle: 'Smart Helmet Navigation',
  taskDesc: 'Navigating to destination…',
  taskIcon: {name: 'ic_launcher', type: 'mipmap'},
  color: '#1a73e8',
  foregroundServiceType: ['connectedDevice', 'location'],
  parameters: {},
};

function App(): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('home');
  const [session, setSession] = useState<NavSession | null>(null);

  const handleNavigationStarted = async (
    sessionId: string,
    route: ParsedRoute,
    origin: LatLon,
    dest: LatLon,
  ) => {
    setSession({sessionId, route, origin, dest});
    setScreen('navigation');

    // Start foreground service so Android doesn't kill us when screen goes off
    try {
      await BackgroundService.start(backgroundTask, backgroundOptions);
    } catch (e) {
      console.warn('Background service start failed (navigation continues):', e);
    }
  };

  const handleStop = async () => {
    try {
      await BackgroundService.stop();
    } catch (_) {}
    setSession(null);
    setScreen('home');
  };

  return (
    <SafeAreaProvider>
      {screen === 'home' && (
        <HomeScreen onNavigationStarted={handleNavigationStarted} />
      )}
      {screen === 'navigation' && session && (
        <NavigationScreen
          sessionId={session.sessionId}
          route={session.route}
          origin={session.origin}
          dest={session.dest}
          onStop={handleStop}
        />
      )}
    </SafeAreaProvider>
  );
}

export default App;
