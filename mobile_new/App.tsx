/**
 * Smart Helmet Navigation — standalone app root.
 * Routes between HomeScreen (route setup) and NavigationScreen (live nav).
<<<<<<< HEAD
 */

import React, { useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import NavigationScreen from './src/screens/NavigationScreen';
import DemoApp from './src/demo/DemoApp';
import type { ParsedRoute, LatLon } from './src/services/routeService';

type Screen = 'home' | 'navigation' | 'demo';
=======
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
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3

interface NavSession {
  sessionId: string;
  route: ParsedRoute;
  origin: LatLon;
  dest: LatLon;
}

<<<<<<< HEAD
=======
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

>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
function App(): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('home');
  const [session, setSession] = useState<NavSession | null>(null);

<<<<<<< HEAD
  const handleNavigationStarted = (
=======
  const handleNavigationStarted = async (
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    sessionId: string,
    route: ParsedRoute,
    origin: LatLon,
    dest: LatLon,
  ) => {
<<<<<<< HEAD
    setSession({ sessionId, route, origin, dest });
    setScreen('navigation');
  };

  const handleStop = () => {
=======
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
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    setSession(null);
    setScreen('home');
  };

  return (
    <SafeAreaProvider>
      {screen === 'home' && (
<<<<<<< HEAD
        <HomeScreen
          onNavigationStarted={handleNavigationStarted}
          onDemo={() => setScreen('demo')}
        />
=======
        <HomeScreen onNavigationStarted={handleNavigationStarted} />
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
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
<<<<<<< HEAD
      {screen === 'demo' && (
        <DemoApp onExit={() => setScreen('home')} />
      )}
=======
>>>>>>> be860fc410b7b5a186f80173c88073a6842371e3
    </SafeAreaProvider>
  );
}

export default App;
