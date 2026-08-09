# Theme Options in Matrix → Customizations

## Status: 🔲 TODO

## Overview

Add a theme picker to the **Matrix → Customizations** tab so users can choose between several themes. The theme infrastructure already exists; the work is to add more themes, wire them into the Customizations UI, and fix the broken/stale bits.

## Current State

- **Customizations tab** (`src/pages/Matrix.jsx:32`) has `component: null` — it only renders hardcoded TacticalPanel variant previews (lines 94-160). No theme selection UI.
- **Theme system already in place**:
  - `src/utils/themes.js` — defines `dark` and `light` themes + `defaultTheme` + `getThemeColors()`.
  - `src/utils/ThemeContext.jsx` — `ThemeProvider` loads theme from `localStorage['alfr3d-theme']`, applies `data-theme` attribute on `<html>`, exposes `currentTheme`/`setCurrentTheme`/`toggleTheme`/`themeColors`.
  - `src/utils/themes.css` — CSS variables for `:root` (dark) and `[data-theme="light"]`.
- **Stale duplicate**: `src/themes.js` contains an unused `default`-only theme; nothing imports it (only `src/utils/themes.js` is used). Consider deleting it.

## Problems to Fix

1. Only 2 themes exist (dark/light). Want several distinct themes to choose from.
2. `toggleTheme` in `ThemeContext.jsx:24-26` is hardcoded to `light`/`dark` and won't work with N themes.
3. `themes.css` CSS variable blocks only cover `:root` and `[data-theme="light"]` — new themes need matching CSS variable sets (comment says the CSS is "Auto-generated from themes.js").
4. `src/themes.js` is a stale duplicate of `src/utils/themes.js`.

## Implementation Plan

1. **Add new themes** to `src/utils/themes.js` and matching `[data-theme="..."]` blocks in `src/utils/themes.css`. Candidate themes:
   - **Dark** (default, existing) — amber/neon dark
   - **Light** (existing)
   - **Neural/Cyan** — the original cyan (#43E3F0) look (see old `default` entry in `src/themes.js`)
   - **Matrix** — green-on-black terminal
   - **Amber** — warm amber
   - **Steel/Graphite** — cold blue-gray
2. **Fix `toggleTheme`** in `ThemeContext.jsx` to cycle themes (or drop it in favor of `setCurrentTheme`) and expose a list of available themes.
3. **Build the Customizations UI** in Matrix.jsx (or a new `src/components/Customizations.jsx`):
   - Grid/list of theme swatches showing preview colors
   - Click to apply → `setCurrentTheme(name)`
   - Persists via existing `localStorage` mechanism
4. **Remove stale `src/themes.js`** (or merge useful values into `src/utils/themes.js`).
5. **Test**: reload page and confirm theme persists; verify each theme's CSS variables apply.

## Files

- `services/service_frontend/src/pages/Matrix.jsx`
- `services/service_frontend/src/utils/themes.js`
- `services/service_frontend/src/utils/themes.css`
- `services/service_frontend/src/utils/ThemeContext.jsx`
- `services/service_frontend/src/themes.js` (remove/merge)
