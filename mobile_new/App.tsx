/**
 * Smart Helmet Navigation — standalone app root.
 * Routes between HomeScreen (route setup) and NavigationScreen (live nav).
 */

import React, {useState} from 'react';
import {SafeAreaProvider} from 'react-native-safe-area-context';
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

function App(): React.JSX.Element {
  const [screen, setScreen] = useState<Screen>('home');
  const [session, setSession] = useState<NavSession | null>(null);

  const handleNavigationStarted = (
    sessionId: string,
    route: ParsedRoute,
    origin: LatLon,
    dest: LatLon,
  ) => {
    setSession({sessionId, route, origin, dest});
    setScreen('navigation');
  };

  const handleStop = () => {
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
