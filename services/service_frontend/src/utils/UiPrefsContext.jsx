import { createContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { NEXUS_NAV_MODES, defaultNexusNav, NEXUS_NAV_STORAGE_KEY } from './nexusNav';
import { KANJI_WISDOM_STORAGE_KEY, defaultKanjiWisdom } from './kanjiWisdom';

// UI preferences that are not colours. The theme has its own provider (ThemeContext);
// this one holds the layout choices a person makes about how a surface is driven. Right
// now that is `nexusNav` (see `nexusNav.js` for what the modes mean) and the `kanjiWisdom`
// on/off switch for the daily kanji quote overlay.

const UiPrefsContext = createContext();

const getInitialNexusNav = () => {
  try {
    const saved = localStorage.getItem(NEXUS_NAV_STORAGE_KEY);
    return NEXUS_NAV_MODES.includes(saved) ? saved : defaultNexusNav;
  } catch {
    return defaultNexusNav;
  }
};

const getInitialKanjiWisdom = () => {
  try {
    const saved = localStorage.getItem(KANJI_WISDOM_STORAGE_KEY);
    return saved === null ? defaultKanjiWisdom : saved === 'true';
  } catch {
    return defaultKanjiWisdom;
  }
};

export const UiPrefsProvider = ({ children }) => {
  const [nexusNav, setNexusNav] = useState(getInitialNexusNav);
  const [kanjiWisdom, setKanjiWisdom] = useState(getInitialKanjiWisdom);

  useEffect(() => {
    try {
      localStorage.setItem(NEXUS_NAV_STORAGE_KEY, nexusNav);
    } catch {
      // A blocked or full store just means the choice lasts this session.
    }
  }, [nexusNav]);

  useEffect(() => {
    try {
      localStorage.setItem(KANJI_WISDOM_STORAGE_KEY, String(kanjiWisdom));
    } catch {
      // Same as above: the choice just lasts this session.
    }
  }, [kanjiWisdom]);

  const value = { nexusNav, setNexusNav, kanjiWisdom, setKanjiWisdom };

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
