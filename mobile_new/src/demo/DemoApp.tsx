/**
 * DemoApp — self-contained demo flow.
 * State machine: preview → running → (back) preview
 * Mounted by App.tsx when the user taps "Demo" on HomeScreen.
 */

import React, {useState} from 'react';
import DemoHomeScreen from './DemoHomeScreen';
import DemoNavigationScreen from './DemoNavigationScreen';

interface Props {
  onExit: () => void;
}

type DemoScreen = 'preview' | 'running';

const DemoApp: React.FC<Props> = ({onExit}) => {
  const [screen, setScreen] = useState<DemoScreen>('preview');

  if (screen === 'preview') {
    return (
      <DemoHomeScreen
        onStart={() => setScreen('running')}
        onBack={onExit}
      />
    );
  }

  return (
    <DemoNavigationScreen
      onStop={() => setScreen('preview')}
    />
  );
};

export default DemoApp;
