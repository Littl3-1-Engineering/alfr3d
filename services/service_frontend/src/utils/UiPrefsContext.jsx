import { createContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { NEXUS_NAV_MODES, defaultNexusNav, NEXUS_NAV_STORAGE_KEY } from './nexusNav';

// UI preferences that are not colours. The theme has its own provider (ThemeContext);
// this one holds the layout choices a person makes about how a surface is driven. Right
// now that is `nexusNav` alone -- see `nexusNav.js` for what the modes mean.

const UiPrefsContext = createContext();

const getInitialNexusNav = () => {
  try {
    const saved = localStorage.getItem(NEXUS_NAV_STORAGE_KEY);
    return NEXUS_NAV_MODES.includes(saved) ? saved : defaultNexusNav;
  } catch {
    return defaultNexusNav;
  }
};

export const UiPrefsProvider = ({ children }) => {
  const [nexusNav, setNexusNav] = useState(getInitialNexusNav);

  useEffect(() => {
    try {
      localStorage.setItem(NEXUS_NAV_STORAGE_KEY, nexusNav);
    } catch {
      // A blocked or full store just means the choice lasts this session.
    }
  }, [nexusNav]);

  const value = { nexusNav, setNexusNav };

  return (
    <UiPrefsContext.Provider value={value}>
      {children}
    </UiPrefsContext.Provider>
  );
};

UiPrefsProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

export default UiPrefsContext;
