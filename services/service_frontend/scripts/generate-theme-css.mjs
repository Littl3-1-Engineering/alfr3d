#!/usr/bin/env node
/**
 * Generates src/utils/themes.css from src/utils/themes.js (single source of truth).
 *
 * Run: npm run generate:theme  (also wired into predev / prebuild)
 */
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { themes } from '../src/utils/themes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_PATH = join(__dirname, '..', 'src', 'utils', 'themes.css');

function parseColor(colorStr) {
  colorStr = colorStr.trim();
  let m = colorStr.match(/^hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%\s*(?:,\s*([\d.]+)\s*)?\)$/i);
  if (m) {
    return { h: +m[1], s: +m[2], l: +m[3], a: m[4] !== undefined ? +m[4] : 1 };
  }
  m = colorStr.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const r = parseInt(m[1].slice(0, 2), 16);
    const g = parseInt(m[1].slice(2, 4), 16);
    const b = parseInt(m[1].slice(4, 6), 16);
    return { ...rgbToHsl(r, g, b), a: 1 };
  }
  throw new Error(`Unsupported color format in themes.js: ${colorStr}`);
}

function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h;
  let s;
  const l = (max + min) / 2;
  if (max === min) {
    h = 0;
    s = 0;
  } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return { h: h * 360, s: s * 100, l: l * 100 };
}

function hslToRgb(h, s, l) {
  s /= 100;
  l /= 100;
  const k = n => (n + h / 30) % 12;
  const a = s * Math.min(l, 1 - l);
  const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return {
    r: Math.round(255 * f(0)),
    g: Math.round(255 * f(8)),
    b: Math.round(255 * f(4)),
  };
}

function withAlpha(color, alpha) {
  return `hsla(${color.h}, ${color.s}%, ${color.l}%, ${alpha})`;
}

function toHex(color) {
  const { r, g, b } = hslToRgb(color.h, color.s, color.l);
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('').toUpperCase();
}

function toRgbTriplet(colorStr) {
  const c = parseColor(colorStr);
  const { r, g, b } = hslToRgb(c.h, c.s, c.l);
  return `${r} ${g} ${b}`;
}

const NAME_MAP = {
  bg: 'background',
  bgSecondary: 'background-secondary',
  bgTertiary: 'background-tertiary',
  primary: 'primary',
  primaryHover: 'primary-hover',
  primaryLight: 'primary-light',
  secondary: 'secondary',
  secondaryHover: 'secondary-hover',
  secondaryLight: 'secondary-light',
  accent: 'accent',
  accentHover: 'accent-hover',
  accentLight: 'accent-light',
  env: 'env',
  envLight: 'env-light',
  envBorder: 'env-border',
  magenta: 'magenta',
  magentaLight: 'magenta-light',
  textPrimary: 'text-primary',
  textSecondary: 'text-secondary',
  textTertiary: 'text-tertiary',
  textInverse: 'text-inverse',
  border: 'border',
  borderActive: 'border-active',
  borderSecondary: 'border-secondary',
  glow: 'glow',
  success: 'success',
  warning: 'warning',
  warningLight: 'warning-light',
  error: 'error',
  info: 'info',
  card: 'card',
  cardHover: 'card-hover',
  cardBorder: 'card-border',
  input: 'input',
  inputBorder: 'input-border',
  inputFocus: 'input-focus',
  backdrop: 'backdrop',
};

function themeBlock(themeName, selector, theme) {
  const lines = [
    `/* ${themeName === 'dark' ? 'Dark theme (default)' : 'Light theme'} */`,
    `${selector} {`,
  ];
  for (const key of Object.keys(NAME_MAP)) {
    lines.push(`  --theme-${NAME_MAP[key]}: ${theme[key]};`);
  }
  for (const [k, v] of Object.entries(theme.tactical)) {
    lines.push(`  --theme-tactical-${k}: ${v};`);
  }
  lines.push(`  --theme-card-rgb: ${toRgbTriplet(theme.card)};`);
  lines.push(`  --theme-border-rgb: ${toRgbTriplet(theme.border)};`);
  const primary = parseColor(theme.primary);
  lines.push(
    `  --theme-grid-image: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><text x="20" y="20" text-anchor="middle" dominant-baseline="middle" font-size="12" fill="${withAlpha(primary, 0.1)}">+</text></svg>');`
  );
  lines.push(
    `  --theme-select-chevron: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23${toHex(primary).slice(1)}' d='M6 8L1 3h10z'/%3E%3C/svg%3E");`
  );
  lines.push('}');
  return lines.join('\n');
}

const LEAFLET = `/* Leaflet Map Dark Theme Overrides */
.leaflet-control-container .leaflet-routing-container-hide {
  display: none;
}

.leaflet-control-container .leaflet-control {
  background-color: var(--theme-card) !important;
  border: 1px solid color-mix(in srgb, var(--theme-primary) 40%, transparent) !important;
  border-radius: 0 !important;
}

.leaflet-control-container .leaflet-control a {
  color: var(--theme-text-primary) !important;
  background-color: transparent !important;
}

.leaflet-control-container .leaflet-control a:hover {
  background-color: color-mix(in srgb, var(--theme-primary) 10%, transparent) !important;
}

.leaflet-control-attribution {
  background-color: var(--theme-card) !important;
  color: var(--theme-text-secondary) !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 10px !important;
}

.leaflet-control-attribution a {
  color: var(--theme-text-secondary) !important;
}`;

const header = `/* AUTO-GENERATED from src/utils/themes.js — do not edit by hand. Run: npm run generate:theme */
/* Single source of truth: services/service_frontend/src/utils/themes.js */`;

const css = [
  header,
  themeBlock('dark', ':root', themes.dark),
  themeBlock('light', '[data-theme="light"]', themes.light),
  LEAFLET,
].join('\n\n') + '\n';

writeFileSync(OUT_PATH, css, 'utf8');
console.log(`Generated ${OUT_PATH}`);
