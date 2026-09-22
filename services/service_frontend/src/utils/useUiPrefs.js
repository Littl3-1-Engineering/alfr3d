import { useContext } from 'react';
import UiPrefsContext from './UiPrefsContext';

export const useUiPrefs = () => {
  const context = useContext(UiPrefsContext);
  if (!context) {
    throw new Error('useUiPrefs must be used within a UiPrefsProvider');
  }
  return context;
};
