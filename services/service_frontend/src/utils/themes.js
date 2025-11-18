// Theme configuration for ALFR3D frontend
// Colors are defined in HSL format for Tailwind CSS compatibility
// Dark theme is the default (matches themes.css)

export const themes = {
  dark: {
    // Background colors - ultra-deep charcoal
    background: 'hsl(220, 25%, 6%)',
    backgroundSecondary: 'hsl(220, 20%, 9%)',
    backgroundTertiary: 'hsl(220, 18%, 12%)',

    // Primary colors - electric amber/yellow
    primary: 'hsl(45, 100%, 58%)', // #FFB84D - pure glowing amber
    primaryHover: 'hsl(45, 100%, 65%)',
    primaryLight: 'hsl(45, 80%, 15%)', // dark amber fill for active states

    // Secondary colors - cold steel blue
    secondary: 'hsl(200, 30%, 50%)',
    secondaryHover: 'hsl(200, 35%, 60%)',
    secondaryLight: 'hsl(220, 20%, 9%)',

    // Accent colors (for highlights and CTAs)
    accent: 'hsl(190, 80%, 45%)', // subtle cyan nod to original theme
    accentHover: 'hsl(190, 85%, 50%)',
    accentLight: 'hsl(220, 20%, 9%)',

    // Text colors - high-contrast off-white with slight blue tint
    textPrimary: 'hsl(200, 20%, 92%)',
    textSecondary: 'hsl(200, 15%, 70%)',
    textTertiary: 'hsl(200, 10%, 50%)',
    textInverse: 'hsl(0, 0%, 100%)',

    // Border colors - glowing amber edges
    border: 'hsla(45, 100%, 58%, 0.4)',
    borderSecondary: 'hsla(45, 100%, 58%, 0.15)',

    // Status colors
    success: 'hsl(190, 80%, 45%)', // subtle cyan
    warning: 'hsl(45, 100%, 58%)', // bright amber
    error: 'hsl(330, 90%, 65%)', // magenta for critical
    info: 'hsl(200, 30%, 50%)', // steel blue

     // Card and surface colors - dark transparent with amber border glow
     card: 'hsla(210, 8%, 4%, 0.65)',
    cardHover: 'hsla(220, 25%, 10%, 0.85)',

    // Input colors
    input: 'hsla(220, 25%, 8%, 0.75)',
    inputBorder: 'hsla(45, 100%, 58%, 0.4)',
    inputFocus: 'hsl(45, 100%, 58%)',
  },

  light: {
    // Background colors
    background: 'hsl(222, 84%, 5%)',
    backgroundSecondary: 'hsl(217, 33%, 17%)',
    backgroundTertiary: 'hsl(217, 33%, 20%)',

    // Primary colors
    primary: 'hsl(217, 91%, 60%)',
    primaryHover: 'hsl(217, 91%, 65%)',
    primaryLight: 'hsl(217, 33%, 17%)',

    // Accent colors
    accent: 'hsl(142, 76%, 45%)',
    accentHover: 'hsl(142, 76%, 50%)',
    accentLight: 'hsl(217, 33%, 17%)',

    // Secondary colors
    secondary: 'hsl(262, 83%, 65%)',
    secondaryHover: 'hsl(262, 83%, 70%)',
    secondaryLight: 'hsl(217, 33%, 17%)',

    // Text colors
    textPrimary: 'hsl(210, 40%, 98%)',
    textSecondary: 'hsl(215, 16%, 65%)',
    textTertiary: 'hsl(215, 16%, 47%)',
    textInverse: 'hsl(222, 84%, 5%)',

    // Border colors
    border: 'hsl(217, 33%, 25%)',
    borderSecondary: 'hsl(217, 33%, 30%)',

    // Status colors
    success: 'hsl(142, 76%, 45%)',
    warning: 'hsl(38, 92%, 55%)',
    error: 'hsl(0, 84%, 65%)',
    info: 'hsl(217, 91%, 65%)',

    // Card and surface colors
    card: 'hsl(217, 33%, 17%)',
    cardHover: 'hsl(217, 33%, 20%)',

    // Input colors
    input: 'hsl(217, 33%, 17%)',
    inputBorder: 'hsl(217, 33%, 25%)',
    inputFocus: 'hsl(217, 91%, 60%)',
  }
};

// Default theme - dark (matches themes.css)
export const defaultTheme = 'dark';

// Helper function to get current theme colors
export const getThemeColors = (themeName = defaultTheme) => {
  return themes[themeName] || themes[defaultTheme];
};