import { themes, boot } from './src/utils/themes.js';

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'exo2': ['Exo 2', 'sans-serif'],
        'tech': ['Rajdhani', 'sans-serif'],
        'mono': ['JetBrains Mono', 'monospace'],
      },
      colors: {
        // Theme-aware colors (dark theme as default)
        background: {
          DEFAULT: themes.dark.bg,
          secondary: themes.dark.bgSecondary,
          tertiary: themes.dark.bgTertiary,
        },
        primary: {
          DEFAULT: themes.dark.primary,
          hover: themes.dark.primaryHover,
          light: themes.dark.primaryLight,
        },
        accent: {
          DEFAULT: themes.dark.accent,
          hover: themes.dark.accentHover,
          light: themes.dark.accentLight,
        },
        secondary: {
          DEFAULT: themes.dark.secondary,
          hover: themes.dark.secondaryHover,
          light: themes.dark.secondaryLight,
        },
        env: {
          DEFAULT: themes.dark.env,
          light: themes.dark.envLight,
          border: themes.dark.envBorder,
        },
        magenta: {
          DEFAULT: themes.dark.magenta,
          light: themes.dark.magentaLight,
        },
        text: {
          primary: themes.dark.textPrimary,
          secondary: themes.dark.textSecondary,
          tertiary: themes.dark.textTertiary,
          inverse: themes.dark.textInverse,
        },
        border: {
          DEFAULT: themes.dark.border,
          secondary: themes.dark.borderSecondary,
        },
        success: themes.dark.success,
        warning: themes.dark.warning,
        error: themes.dark.error,
        info: themes.dark.info,
        card: {
          DEFAULT: themes.dark.card,
          hover: themes.dark.cardHover,
        },
        input: {
          DEFAULT: themes.dark.input,
          border: themes.dark.inputBorder,
          focus: themes.dark.inputFocus,
        },
        // Legacy colors for backward compatibility
        'navy-dark': '#0d1117',
        'charcoal': '#05070A',
        // Tactical FUI colors
        fui: {
          bg: themes.dark.tactical.bg,       // Deep navy
          panel: themes.dark.tactical.panel, // Slightly lighter panel bg
          border: themes.dark.tactical.border, // Grey borders
          accent: themes.dark.tactical.accent, // Cyan accent
          magenta: themes.dark.magenta,      // Magenta secondary
          env: themes.dark.env,              // Yellow env accent
          text: themes.dark.tactical.text,   // Muted text
          dim: themes.dark.tactical.dim,     // Dim cyan background
          grid: themes.dark.tactical.grid,   // Grid lines
        },
        // Boot / terminal identity palette
        boot: boot,
      },
       backgroundImage: {
         'tech-grid': `linear-gradient(to right, ${themes.dark.tactical.grid} 1px, transparent 1px), linear-gradient(to bottom, ${themes.dark.tactical.grid} 1px, transparent 1px)`,
       }
    },
  },
  plugins: [],
}
