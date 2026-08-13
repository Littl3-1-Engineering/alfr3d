import { createContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { themes, defaultTheme, getThemeColors } from './themes';

const ThemeContext = createContext();

// Resolve the saved theme synchronously so the UI (including the initial loading
// screen) renders in the correct theme from the very first paint.
const getInitialTheme = () => {
  try {
    const savedTheme = localStorage.getItem('alfr3d-theme');
    return savedTheme && themes[savedTheme] ? savedTheme : defaultTheme;
  } catch {
    return defaultTheme;
  }
};

// Apply before first paint to avoid a flash of the default theme on load.
document.documentElement.setAttribute('data-theme', getInitialTheme());

export const ThemeProvider = ({ children }) => {
  const [currentTheme, setCurrentTheme] = useState(getInitialTheme);

  useEffect(() => {
    // Apply theme to document
    document.documentElement.setAttribute('data-theme', currentTheme);
    localStorage.setItem('alfr3d-theme', currentTheme);
  }, [currentTheme]);

  const toggleTheme = () => {
    const order = Object.keys(themes);
    setCurrentTheme(prevTheme => {
      const idx = order.indexOf(prevTheme);
      return order[(idx + 1) % order.length];
    });
  };

  const themeColors = getThemeColors(currentTheme);

  const value = {
    currentTheme,
    setCurrentTheme,
    toggleTheme,
    themeColors,
    themes
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};

ThemeProvider.propTypes = {
  children: PropTypes.node.isRequired,
};

export default ThemeContext;
