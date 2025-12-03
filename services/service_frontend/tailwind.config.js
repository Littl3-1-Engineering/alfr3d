import { themes } from './src/utils/themes.js';

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
          DEFAULT: themes.dark.background,
          secondary: themes.dark.backgroundSecondary,
          tertiary: themes.dark.backgroundTertiary,
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
        'navy-dark': '#0A0F14',
        'charcoal': '#05070A',
        // Tactical FUI colors
        'fui-bg': '#0b0c0f',       // Deep matte black
        'fui-panel': '#141619',    // Slightly lighter panel bg
        'fui-border': '#33363d',   // Grey borders
        'fui-accent': '#eab308',   // Amber/Yellow accent
        'fui-text': '#94a3b8',     // Muted text
        'fui-dim': 'rgba(234, 179, 8, 0.1)', // Dim amber background
        'fui-grid': '#222',        // Grid lines
      },
       backgroundImage: {
         'tech-grid': "linear-gradient(to right, #222 1px, transparent 1px), linear-gradient(to bottom, #222 1px, transparent 1px)",
       }
    },
  },
  plugins: [],
}
