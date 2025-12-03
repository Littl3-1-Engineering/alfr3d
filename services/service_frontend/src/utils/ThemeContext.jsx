import { createContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { themes, defaultTheme, getThemeColors } from './themes';

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
  const [currentTheme, setCurrentTheme] = useState(defaultTheme);

  useEffect(() => {
    // Load theme from localStorage on mount
    const savedTheme = localStorage.getItem('alfr3d-theme');
    if (savedTheme && themes[savedTheme]) {
      setCurrentTheme(savedTheme);
    }
  }, []);

  useEffect(() => {
    // Apply theme to document
    document.documentElement.setAttribute('data-theme', currentTheme);
    localStorage.setItem('alfr3d-theme', currentTheme);
  }, [currentTheme]);

  const toggleTheme = () => {
    setCurrentTheme(prevTheme => prevTheme === 'light' ? 'dark' : 'light');
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
