/**
 * Smart Helmet App — Root
 *
 * Simple screen switcher:  HomeScreen  ⇄  NavigationScreen
 *
 * HomeScreen sends START_NAVIGATION to NCS (which calls OSRM internally).
 * NCS returns an initial UIStateMessage; NavigationScreen polls NCS for updates.
 */

import React, {useState} from 'react';
import {SafeAreaProvider} from 'react-native-safe-area-context';
import HomeScreen from './src/screens/HomeScreen';
import NavigationScreen from './src/screens/NavigationScreen';
import {UIStateMessage} from './src/types';

type AppState =
  | {screen: 'home'}
  | {screen: 'navigation'; sessionId: string; initialState: UIStateMessage | null};

function App(): React.JSX.Element {
  const [state, setState] = useState<AppState>({screen: 'home'});

  if (state.screen === 'navigation') {
    return (
      <SafeAreaProvider>
        <NavigationScreen
          sessionId={state.sessionId}
          initialState={state.initialState}
          onStop={() => setState({screen: 'home'})}
        />
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <HomeScreen
        onNavigationStarted={(sessionId, initialState) =>
          setState({screen: 'navigation', sessionId, initialState})
        }
      />
    </SafeAreaProvider>
  );
}

export default App;
