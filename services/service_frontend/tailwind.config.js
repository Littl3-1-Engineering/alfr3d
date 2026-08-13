import { boot } from './src/utils/themes.js';

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
        // Theme-aware colors — driven by generated CSS custom properties so the
        // active theme (dark/amber/light) re-themes the whole UI at runtime.
        // Tailwind v3 (no color-mix) needs the RGB-channel pattern so opacity
        // modifiers like `bg-primary/20` keep working when themes switch.
        background: {
          DEFAULT: 'rgb(var(--theme-background-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--theme-background-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--theme-background-tertiary-rgb) / <alpha-value>)',
        },
        primary: {
          DEFAULT: 'rgb(var(--theme-primary-rgb) / <alpha-value>)',
          hover: 'rgb(var(--theme-primary-hover-rgb) / <alpha-value>)',
          light: 'rgb(var(--theme-primary-light-rgb) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--theme-accent-rgb) / <alpha-value>)',
          hover: 'rgb(var(--theme-accent-hover-rgb) / <alpha-value>)',
          light: 'rgb(var(--theme-accent-light-rgb) / <alpha-value>)',
        },
        secondary: {
          DEFAULT: 'rgb(var(--theme-secondary-rgb) / <alpha-value>)',
          hover: 'rgb(var(--theme-secondary-hover-rgb) / <alpha-value>)',
          light: 'rgb(var(--theme-secondary-light-rgb) / <alpha-value>)',
        },
        env: {
          DEFAULT: 'rgb(var(--theme-env-rgb) / <alpha-value>)',
          light: 'rgb(var(--theme-env-light-rgb) / <alpha-value>)',
          border: 'rgb(var(--theme-env-border-rgb) / <alpha-value>)',
        },
        magenta: {
          DEFAULT: 'rgb(var(--theme-magenta-rgb) / <alpha-value>)',
          light: 'rgb(var(--theme-magenta-light-rgb) / <alpha-value>)',
        },
        text: {
          primary: 'rgb(var(--theme-text-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--theme-text-secondary-rgb) / <alpha-value>)',
          tertiary: 'rgb(var(--theme-text-tertiary-rgb) / <alpha-value>)',
          inverse: 'rgb(var(--theme-text-inverse-rgb) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--theme-border-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--theme-border-secondary-rgb) / <alpha-value>)',
        },
        success: 'rgb(var(--theme-success-rgb) / <alpha-value>)',
        warning: 'rgb(var(--theme-warning-rgb) / <alpha-value>)',
        error: 'rgb(var(--theme-error-rgb) / <alpha-value>)',
        info: 'rgb(var(--theme-info-rgb) / <alpha-value>)',
        card: {
          DEFAULT: 'rgb(var(--theme-card-rgb) / <alpha-value>)',
          hover: 'rgb(var(--theme-card-hover-rgb) / <alpha-value>)',
        },
        input: {
          DEFAULT: 'rgb(var(--theme-input-rgb) / <alpha-value>)',
          border: 'rgb(var(--theme-input-border-rgb) / <alpha-value>)',
          focus: 'rgb(var(--theme-input-focus-rgb) / <alpha-value>)',
        },
        // Legacy colors for backward compatibility
        'navy-dark': '#0d1117',
        'charcoal': '#05070A',
        // Tactical FUI colors — runtime-themeable
        fui: {
          bg: 'rgb(var(--theme-tactical-bg-rgb) / <alpha-value>)',
          panel: 'rgb(var(--theme-tactical-panel-rgb) / <alpha-value>)',
          border: 'rgb(var(--theme-tactical-border-rgb) / <alpha-value>)',
          accent: 'rgb(var(--theme-tactical-accent-rgb) / <alpha-value>)',
          magenta: 'rgb(var(--theme-magenta-rgb) / <alpha-value>)',
          env: 'rgb(var(--theme-env-rgb) / <alpha-value>)',
          text: 'rgb(var(--theme-tactical-text-rgb) / <alpha-value>)',
          dim: 'rgb(var(--theme-tactical-dim-rgb) / <alpha-value>)',
          grid: 'rgb(var(--theme-tactical-grid-rgb) / <alpha-value>)',
        },
        // Boot / terminal identity palette
        boot: boot,
      },
       backgroundImage: {
         'tech-grid': `linear-gradient(to right, var(--theme-tactical-grid) 1px, transparent 1px), linear-gradient(to bottom, var(--theme-tactical-grid) 1px, transparent 1px)`,
       }
    },
  },
  plugins: [],
}
