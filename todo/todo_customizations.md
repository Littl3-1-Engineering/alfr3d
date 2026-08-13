# @todo Customizations: Theme Options on the Matrix Page

> **STATUS: IMPLEMENTED** — theme picker on Matrix > Customizations; three themes
> (`dark` = cyan default, `amber` = charcoal/amber restored, `light` = white/gray
> with teal + red highlights). Tailwind semantic colors are now runtime-themeable.

## Goal

Give the Matrix page a Customizations tab that lets the user switch UI themes. The
current cyan-heavy dark theme stays the default. Two more themes are offered:

1. **Cyan / Navy** (`dark`) — current default. Deep navy substrate, glowing cyan
   primary/accent, magenta secondary.
2. **Amber / Charcoal** (`amber`) — restores the pre-cyan theme: ultra-deep charcoal
   substrate with electric amber primary and steel-blue secondary.
3. **Light / Teal** (`light`) — redesigned light theme: whites and grays with teal
   as the primary accent and red as the secondary/error highlight.

## Source of Truth

All color tokens live in `services/service_frontend/src/utils/themes.js`. `themes.css`
is generated via `npm run generate:theme` (wired into `predev`/`prebuild`). Tailwind
semantic classes are driven by generated `--theme-*-rgb` channel triplets so opacity
modifiers keep working when the `data-theme` attribute on `<html>` switches themes
(Tailwind v3 has no `color-mix`, so alpha-baked tokens are pre-composited over the
theme background by the generator).

## Tasks

### Phase 1: Tokens
- [x] Add `amber` theme to `themes.js` (flat schema identical to `dark`/`light`):
  - Substrate: deep charcoal (`hsl(220, 25%, 6%)` → `#0b0c0f` tactical)
  - Primary/env/accent: electric amber `hsl(45, 100%, 58%)` / `#eab308`
  - Secondary: steel blue `hsl(200, 30%, 50%)`
  - Borders/glow/input: amber-tinted; success = cyan, error = magenta
- [x] Redesign `light` theme in `themes.js`:
  - Base: whites/gray (`hsl(210, 20%, 98%)` bg → white cards)
  - Primary/accent: teal (`hsl(180, 90%, 32%)` / tactical `#0d9488`)
  - Secondary/error: red (`hsl(0, 72%, 51%)` / `#dc2626`)
  - env stays amber/yellow (sun/location semantic)
- [x] Keep `dark` (cyan) unchanged as `defaultTheme`.

### Phase 2: CSS Generation
- [x] Generalize `scripts/generate-theme-css.mjs` to emit a block per theme:
  - `:root` for `dark` (default), `[data-theme="amber"]`, `[data-theme="light"]`
  - Emits `--theme-*-rgb` channel triplets for every token (alpha-composited over
    the theme bg); added `rgba()`/`rgb()` and 3-digit hex parsing
- [x] Regenerate `src/utils/themes.css` and commit it.

### Phase 3: Runtime
- [x] `ThemeContext.jsx`: `toggleTheme` cycles `dark → amber → light → dark`
      (kept `setCurrentTheme` for direct selection).
- [x] `tailwind.config.js`: semantic/fui colors reference `rgb(var(--theme-*-rgb) / <alpha-value>)`
      so the active theme re-themes the whole UI (incl. `/opacity` modifiers).
- [x] `Matrix.jsx` Customizations tab: theme selector grid (name + swatches +
      active state) via new `ThemeCustomization.jsx`; panel-variant gallery kept below.

### Phase 4: Verification
- [x] `npm run lint`, `npm run test`, `npm run build` pass in `service_frontend`
      (lint issues that remain are pre-existing in unrelated files).
- [x] Manual: switch between all three themes, check panels, buttons, grid, map,
      select chevrons, glows.
