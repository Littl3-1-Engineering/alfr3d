// Theme configuration for ALFR3D frontend
// =======================================
// SINGLE SOURCE OF TRUTH for all colors.
// - tailwind.config.js imports tokens for Tailwind utilities
// - scripts/generate-theme-css.mjs generates src/utils/themes.css (CSS custom properties)
//   from the same tokens, so the two can never drift apart.
// - ThemeContext.jsx exposes tokens for dynamic inline SVG styling only.
// Do NOT add hardcoded colors in components; use Tailwind semantic classes,
// var(--theme-*), or these tokens.
//
// Colors are defined in HSL format for Tailwind CSS compatibility.
// Dark theme is the default (matches generated themes.css).

export const themes = {
  dark: {
    // Substrate colors - deep navy/charcoal
    bg: '#0d1117',            // GitHub-dark navy
    bgSecondary: '#161b22',   // Slightly lighter navy
    bgTertiary: '#21262d',    // Raised surface

    // Primary colors - neural cyan
    primary: 'hsl(188, 93%, 43%)', // #06b6d4 - glowing cyan
    primaryHover: 'hsl(188, 93%, 52%)',
    primaryLight: 'hsl(188, 80%, 14%)', // dark cyan fill for active states

    // Secondary colors - magenta
    secondary: 'hsl(330, 90%, 61%)', // #ec4899
    secondaryHover: 'hsl(330, 90%, 70%)',
    secondaryLight: 'hsl(330, 80%, 16%)',

    // Accent colors (for highlights and CTAs)
    accent: 'hsl(190, 95%, 55%)', // neon cyan
    accentHover: 'hsl(190, 95%, 62%)',
    accentLight: 'hsl(190, 80%, 12%)',

    // Environmental accent - amber/yellow (sun, location, environment)
    env: '#eab308',
    envLight: 'hsl(45, 80%, 18%)',
    envBorder: 'hsla(45, 100%, 58%, 0.35)',

    // Secondary brand accent - magenta
    magenta: '#ec4899',
    magentaLight: 'hsla(330, 90%, 65%, 0.15)',

    // Text colors - high-contrast off-white with slight blue tint
    textPrimary: 'hsl(200, 20%, 92%)',
    textSecondary: 'hsl(200, 15%, 70%)',
    textTertiary: 'hsl(200, 10%, 50%)',
    textInverse: 'hsl(0, 0%, 100%)',

    // Border colors - glowing cyan edges
    border: 'hsla(188, 93%, 43%, 0.4)',
    borderActive: 'hsl(188, 93%, 43%)',
    borderSecondary: 'hsla(188, 93%, 43%, 0.15)',

    // Glow color - used for drop-shadows and halos
    glow: 'hsla(188, 93%, 43%, 0.6)',

    // Status colors
    success: 'hsl(142, 76%, 45%)', // green
    warning: 'hsl(45, 100%, 58%)', // bright yellow (env)
    warningLight: 'hsl(45, 80%, 18%)',
    error: 'hsl(330, 90%, 65%)', // magenta for critical
    info: 'hsl(200, 30%, 50%)', // steel blue

    // Card and surface colors - dark transparent with cyan border glow
    card: 'hsla(210, 8%, 4%, 0.65)',
    cardHover: 'hsla(212, 26%, 12%, 0.85)',
    cardBorder: 'hsla(188, 93%, 43%, 0.35)',

    // Input colors
    input: 'hsla(212, 26%, 8%, 0.75)',
    inputBorder: 'hsla(188, 93%, 43%, 0.4)',
    inputFocus: 'hsl(188, 93%, 43%)',

    // Backdrop blur overlay
    backdrop: 'hsla(212, 30%, 4%, 0.85)',

    // Tactical FUI additions
    tactical: {
      bg: '#0d1117',       // Deep navy
      panel: '#161b22',    // Slightly lighter panel bg
      border: '#30363d',   // Grey borders
      accent: '#06b6d4',   // Cyan accent
      text: '#94a3b8',     // Muted text
      dim: 'rgba(6, 182, 212, 0.1)', // Dim cyan background
      grid: '#1f242b',     // Grid lines
    }
  },

  amber: {
    // Substrate colors - ultra-deep charcoal
    bg: 'hsl(220, 25%, 6%)',
    bgSecondary: 'hsl(220, 20%, 9%)',
    bgTertiary: 'hsl(220, 18%, 12%)',

    // Primary colors - electric amber
    primary: 'hsl(45, 100%, 58%)', // #FFB84D - pure glowing amber
    primaryHover: 'hsl(45, 100%, 65%)',
    primaryLight: 'hsl(45, 80%, 15%)', // dark amber fill for active states

    // Secondary colors - cold steel blue
    secondary: 'hsl(200, 30%, 50%)',
    secondaryHover: 'hsl(200, 35%, 60%)',
    secondaryLight: 'hsl(220, 20%, 9%)',

    // Accent colors - subtle cyan nod to the cyan theme
    accent: 'hsl(190, 80%, 45%)',
    accentHover: 'hsl(190, 85%, 50%)',
    accentLight: 'hsl(220, 20%, 9%)',

    // Environmental accent - amber/yellow
    env: '#eab308',
    envLight: 'hsl(45, 80%, 18%)',
    envBorder: 'hsla(45, 100%, 58%, 0.35)',

    // Secondary brand accent - magenta
    magenta: '#ec4899',
    magentaLight: 'hsla(330, 90%, 65%, 0.15)',

    // Text colors - high-contrast off-white with slight blue tint
    textPrimary: 'hsl(200, 20%, 92%)',
    textSecondary: 'hsl(200, 15%, 70%)',
    textTertiary: 'hsl(200, 10%, 50%)',
    textInverse: 'hsl(0, 0%, 100%)',

    // Border colors - glowing amber edges
    border: 'hsla(45, 100%, 58%, 0.4)',
    borderActive: 'hsl(45, 100%, 58%)',
    borderSecondary: 'hsla(45, 100%, 58%, 0.15)',

    // Glow color - amber halo
    glow: 'hsla(45, 100%, 58%, 0.6)',

    // Status colors
    success: 'hsl(190, 80%, 45%)', // subtle cyan
    warning: 'hsl(45, 100%, 58%)', // bright amber
    warningLight: 'hsl(45, 80%, 18%)',
    error: 'hsl(330, 90%, 65%)', // magenta for critical
    info: 'hsl(200, 30%, 50%)', // steel blue

    // Card and surface colors - dark transparent with amber border glow
    card: 'hsla(210, 8%, 4%, 0.65)',
    cardHover: 'hsla(220, 25%, 10%, 0.85)',
    cardBorder: 'hsla(45, 100%, 58%, 0.35)',

    // Input colors
    input: 'hsla(220, 25%, 8%, 0.75)',
    inputBorder: 'hsla(45, 100%, 58%, 0.4)',
    inputFocus: 'hsl(45, 100%, 58%)',

    // Backdrop blur overlay
    backdrop: 'hsla(220, 25%, 6%, 0.85)',

    // Tactical FUI additions
    tactical: {
      bg: '#0b0c0f',       // Deep matte charcoal
      panel: '#141619',    // Slightly lighter panel bg
      border: '#33363d',   // Grey borders
      accent: '#eab308',   // Amber/Yellow accent
      text: '#94a3b8',     // Muted text
      dim: 'rgba(234, 179, 8, 0.1)', // Dim amber background
      grid: '#222',        // Grid lines
    }
  },

  light: {
    // Background colors - whites and grays
    bg: 'hsl(210, 20%, 98%)',
    bgSecondary: 'hsl(215, 16%, 94%)',
    bgTertiary: 'hsl(220, 14%, 90%)',

    // Primary colors - teal
    primary: 'hsl(180, 90%, 32%)',
    primaryHover: 'hsl(180, 90%, 40%)',
    primaryLight: 'hsl(180, 70%, 90%)',

    // Accent colors - teal
    accent: 'hsl(174, 72%, 46%)',
    accentHover: 'hsl(174, 72%, 52%)',
    accentLight: 'hsl(174, 80%, 90%)',

    // Secondary colors - red
    secondary: 'hsl(0, 72%, 51%)',
    secondaryHover: 'hsl(0, 72%, 58%)',
    secondaryLight: 'hsl(0, 80%, 94%)',

    // Environmental accent - amber/yellow
    env: '#b45309',
    envLight: 'hsl(45, 80%, 92%)',
    envBorder: 'hsla(45, 100%, 40%, 0.4)',

    // Secondary brand accent - red
    magenta: '#dc2626',
    magentaLight: 'hsla(0, 80%, 55%, 0.15)',

    // Text colors - dark gray
    textPrimary: 'hsl(215, 25%, 15%)',
    textSecondary: 'hsl(215, 16%, 40%)',
    textTertiary: 'hsl(215, 14%, 55%)',
    textInverse: 'hsl(0, 0%, 100%)',

    // Border colors - light gray
    border: 'hsl(215, 16%, 84%)',
    borderActive: 'hsl(180, 90%, 32%)',
    borderSecondary: 'hsl(215, 16%, 88%)',

    // Glow color - soft teal halo
    glow: 'hsla(180, 90%, 32%, 0.35)',

    // Status colors
    success: 'hsl(142, 76%, 40%)',
    warning: 'hsl(45, 90%, 45%)',
    warningLight: 'hsl(45, 90%, 90%)',
    error: 'hsl(0, 72%, 51%)',
    info: 'hsl(200, 60%, 45%)',

    // Card and surface colors - white
    card: 'hsl(0, 0%, 100%)',
    cardHover: 'hsl(210, 20%, 96%)',
    cardBorder: 'hsl(215, 16%, 88%)',

    // Input colors
    input: 'hsl(0, 0%, 100%)',
    inputBorder: 'hsl(215, 16%, 82%)',
    inputFocus: 'hsl(180, 90%, 32%)',

    // Backdrop blur overlay
    backdrop: 'hsla(210, 20%, 98%, 0.9)',

    // Tactical FUI additions for light theme
    tactical: {
      bg: '#f8fafc',       // Light tactical background
      panel: '#ffffff',    // White panels
      border: '#e2e8f0',   // Light grey borders
      accent: '#0d9488',   // Teal-600 accent for light theme
      text: '#475569',     // Muted text
      dim: 'rgba(13, 148, 136, 0.1)', // Dim teal background
      grid: '#e2e8f0',     // Light grid lines
    }
  },

  matrix: {
    // Substrate colors - near-black with a faint green cast
    bg: 'hsl(120, 20%, 3%)',
    bgSecondary: 'hsl(120, 15%, 6%)',
    bgTertiary: 'hsl(120, 12%, 9%)',

    // Primary colors - phosphor green
    primary: 'hsl(135, 95%, 45%)',
    primaryHover: 'hsl(135, 95%, 55%)',
    primaryLight: 'hsl(135, 80%, 12%)', // dark green fill for active states

    // Secondary colors - dimmer lime-green
    secondary: 'hsl(95, 70%, 45%)',
    secondaryHover: 'hsl(95, 70%, 55%)',
    secondaryLight: 'hsl(120, 15%, 8%)',

    // Accent colors - bright terminal lime
    accent: 'hsl(115, 100%, 55%)',
    accentHover: 'hsl(115, 100%, 62%)',
    accentLight: 'hsl(120, 15%, 8%)',

    // Environmental accent - chartreuse (sun, location, environment)
    env: 'hsl(75, 90%, 50%)',
    envLight: 'hsl(75, 60%, 12%)',
    envBorder: 'hsla(75, 90%, 50%, 0.35)',

    // Secondary brand accent - green (keeps the monochrome look)
    magenta: 'hsl(135, 95%, 45%)',
    magentaLight: 'hsla(135, 95%, 45%, 0.15)',

    // Text colors - green-tinted phosphor
    textPrimary: 'hsl(120, 45%, 85%)',
    textSecondary: 'hsl(120, 30%, 65%)',
    textTertiary: 'hsl(120, 20%, 45%)',
    textInverse: 'hsl(120, 20%, 3%)',

    // Border colors - glowing green edges
    border: 'hsla(135, 95%, 45%, 0.4)',
    borderActive: 'hsl(135, 95%, 45%)',
    borderSecondary: 'hsla(135, 95%, 45%, 0.15)',

    // Glow color - green halo
    glow: 'hsla(135, 95%, 45%, 0.6)',

    // Status colors
    success: 'hsl(135, 95%, 45%)', // green
    warning: 'hsl(75, 90%, 50%)',  // chartreuse
    warningLight: 'hsl(75, 60%, 12%)',
    error: 'hsl(0, 85%, 60%)',     // red still reads as an alert
    info: 'hsl(160, 60%, 45%)',    // teal-green

    // Card and surface colors - near-black with green border glow
    card: 'hsla(120, 20%, 3%, 0.65)',
    cardHover: 'hsla(120, 18%, 8%, 0.85)',
    cardBorder: 'hsla(135, 95%, 45%, 0.35)',

    // Input colors
    input: 'hsla(120, 20%, 5%, 0.75)',
    inputBorder: 'hsla(135, 95%, 45%, 0.4)',
    inputFocus: 'hsl(135, 95%, 45%)',

    // Backdrop blur overlay
    backdrop: 'hsla(120, 20%, 3%, 0.85)',

    // Tactical FUI additions
    tactical: {
      bg: '#020402',       // Near-pure black
      panel: '#081008',    // Faint green-black panel
      border: '#1a3a1a',   // Dim green borders
      accent: '#22dd22',   // Terminal green accent
      text: '#7aa87a',     // Muted green text
      dim: 'rgba(34, 221, 34, 0.1)', // Dim green background
      grid: '#0f1f0f',     // Grid lines
    }
  },

  graphite: {
    // Substrate colors - cold blue-gray slate
    bg: 'hsl(215, 18%, 10%)',
    bgSecondary: 'hsl(215, 16%, 14%)',
    bgTertiary: 'hsl(215, 14%, 18%)',

    // Primary colors - steel / ice blue
    primary: 'hsl(205, 70%, 60%)',
    primaryHover: 'hsl(205, 75%, 68%)',
    primaryLight: 'hsl(205, 40%, 20%)', // dark steel fill for active states

    // Secondary colors - muted periwinkle
    secondary: 'hsl(230, 25%, 62%)',
    secondaryHover: 'hsl(230, 30%, 70%)',
    secondaryLight: 'hsl(215, 16%, 16%)',

    // Accent colors - cool cyan-steel
    accent: 'hsl(190, 65%, 58%)',
    accentHover: 'hsl(190, 70%, 65%)',
    accentLight: 'hsl(215, 16%, 16%)',

    // Environmental accent - amber/yellow (sun, location, environment)
    env: '#eab308',
    envLight: 'hsl(45, 50%, 16%)',
    envBorder: 'hsla(45, 90%, 55%, 0.35)',

    // Secondary brand accent - periwinkle
    magenta: 'hsl(230, 25%, 62%)',
    magentaLight: 'hsla(230, 25%, 62%, 0.15)',

    // Text colors - cool off-white
    textPrimary: 'hsl(210, 20%, 90%)',
    textSecondary: 'hsl(210, 14%, 68%)',
    textTertiary: 'hsl(210, 12%, 48%)',
    textInverse: 'hsl(215, 18%, 10%)',

    // Border colors - steel edges
    border: 'hsla(205, 70%, 60%, 0.35)',
    borderActive: 'hsl(205, 70%, 60%)',
    borderSecondary: 'hsla(205, 70%, 60%, 0.14)',

    // Glow color - soft steel halo
    glow: 'hsla(205, 70%, 60%, 0.5)',

    // Status colors
    success: 'hsl(150, 55%, 50%)',
    warning: 'hsl(38, 90%, 58%)',
    warningLight: 'hsl(38, 60%, 16%)',
    error: 'hsl(2, 75%, 62%)',
    info: 'hsl(205, 70%, 60%)',

    // Card and surface colors - cold slate with steel border glow
    card: 'hsla(215, 20%, 7%, 0.65)',
    cardHover: 'hsla(215, 18%, 16%, 0.85)',
    cardBorder: 'hsla(205, 70%, 60%, 0.3)',

    // Input colors
    input: 'hsla(215, 20%, 9%, 0.75)',
    inputBorder: 'hsla(205, 70%, 60%, 0.35)',
    inputFocus: 'hsl(205, 70%, 60%)',

    // Backdrop blur overlay
    backdrop: 'hsla(215, 18%, 8%, 0.85)',

    // Tactical FUI additions
    tactical: {
      bg: '#12161c',       // Cold graphite
      panel: '#1a2028',    // Slightly lighter panel bg
      border: '#333c47',   // Steel-grey borders
      accent: '#5aa9d6',   // Steel-blue accent
      text: '#8b97a6',     // Muted text
      dim: 'rgba(90, 169, 214, 0.1)', // Dim steel background
      grid: '#20262f',     // Grid lines
    }
  }
};

// Boot / terminal identity palette - theme-independent (cyan boot screens, tree viz)
export const boot = {
  bg: '#0a0a0a',       // Boot screen background
  panel: '#1a1a1a',    // Panel background
  panelHover: '#2a2a2a', // Panel hover background
  cyan: '#00FFFF',     // Terminal cyan accent
  orange: '#FF6B00',   // Truncated / warning accent
  gray: '#888888',     // Muted lines
  grayDim: '#555555',  // Dim lines
  white: '#FFFFFF',    // Bright text
  silver: '#CCCCCC',   // Info text
};

// Default theme - dark (matches generated themes.css)
export const defaultTheme = 'dark';

// Helper function to get current theme colors
export const getThemeColors = (themeName = defaultTheme) => {
  return themes[themeName] || themes[defaultTheme];
};
