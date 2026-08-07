# Plan: Centralize Theme Management in a Single Source of Truth

> **STATUS: COMPLETE** (all phases done, lint + build pass; remaining lint errors are pre-existing in unrelated files). Legacy `src/themes.js` deleted. `boot` palette added for the theme-independent cyan boot/terminal identity.

## Goal
Make the frontend theme managed from **one** canonical file so changing a color means editing exactly one place. No visual changes — this is consolidation only (the actual cyan/magenta/yellow re-theme is tracked separately in `implementation_plan.md` Phase 0).

## Current Problem — 3 Sources of Truth + Scattered Hardcodes

1. `services/service_frontend/src/utils/themes.js` — JS theme object (`dark`/`light` + `tactical`). Consumed by `tailwind.config.js`, `ThemeContext.jsx`, and inline SVG styles via `useTheme().themeColors` (Core.jsx, ServiceIntegrity.jsx).
2. `services/service_frontend/src/utils/themes.css` — hand-maintained CSS custom properties. Header claims "Auto-generated from themes.js" but is **not** generated and has **already diverged**:
   - Dark background: CSS `hsl(30, 17%, 6%)` vs JS `hsl(220, 25%, 6%)`
   - Light primary: CSS orange `hsl(24, 100%, 58%)` vs JS blue `hsl(217, 91%, 60%)`
3. `services/service_frontend/tailwind.config.js` — reads `themes.dark.*` for most utilities, but hardcodes the `fui-*` palette as literals (lines 65–71) instead of referencing `themes.dark.tactical`.

Plus hardcoded colors scattered across ~10 files:
- `src/index.css` — 12+ hardcoded amber `hsla(45, 100%, 58%, …)` (grid bg, glass corners, glows, terminal, select chevron `#FFB84D`)
- `src/utils/themes.css` — Leaflet overrides with hardcoded amber
- `TacticalPanelVariant2/4/5/6/7.jsx` — `const amberColor = 'hsl(45, 100%, 58%)'`
- `TacticalPanelVariant3.jsx` — `shadow-[0_0_15px_rgba(234,179,8,0.4)]`
- `LocationPanel.jsx` — `#eab308` (marker, popup, map fillColor)
- `ProjectTreeViz.jsx` — `border: '1px solid #eab308'`
- `Matrix.jsx` — hardcoded text describing the yellow accent

## Target Architecture

**`src/utils/themes.js` = single source of truth.** Everything else derives from it:

```
themes.js (canonical tokens, dark + light)
   ├── tailwind.config.js          → imports themes.js for ALL colors (incl. fui-*, new tokens)
   ├── scripts/generate-theme-css  → emits themes.css (:root / [data-theme="light"] + glows)
   └── ThemeContext.jsx            → getThemeColors() for dynamic inline SVG styling only
```

- CSS custom properties (`--theme-*`) are **generated**, never hand-edited.
- Components use Tailwind semantic classes (e.g. `text-primary`, `bg-card`, `border-border`, `fui-accent`, `text-env`, `text-magenta`) or `var(--theme-*)` in global CSS. No hex/hsl literals.
- `useTheme().themeColors` remains only for dynamic SVG colors that can't be classes (Core.jsx orbits, ServiceIntegrity.jsx).
- Appearance is preserved exactly as today; only indirection changes.

## Phase 0: Canonical Token Schema in themes.js

- Restructure `themes.js` so `dark` and `light` share an identical, flat shape: `bg`, `bgSecondary`, `bgTertiary`, `primary`, `primaryHover`, `primaryLight`, `secondary`, `secondaryHover`, `secondaryLight`, `env`, `envLight`, `envBorder`, `magenta`, `magentaLight`, `textPrimary`, `textSecondary`, `textTertiary`, `textInverse`, `border`, `borderActive`, `borderSecondary`, `card`, `cardHover`, `cardBorder`, `input`, `inputBorder`, `inputFocus`, `backdrop`, `success`, `warning`, `error`, `info`, `glow`, `tactical: { bg, panel, border, accent, text, dim, grid }`.
- Add `env`/`magenta` tokens (pre-populated from existing amber values for now — no visual change).
- Ensure `themes.dark.*` and `themes.light.*` no longer silently disagree (light theme is currently unused but must stay consistent).
- Update `tailwind.config.js`:
  - Replace hardcoded `fui-*` literals with `themes.dark.tactical.*`.
  - Add `env`/`magenta` color utilities mapped from tokens.
  - Fix `tech-grid` backgroundImage to use the `tactical.grid` token.
- Update `ThemeContext.jsx`/`getThemeColors` only if the shape change requires it (keep API stable).

## Phase 1: CSS Generator

- Create `scripts/generate-theme-css.mjs` that imports `src/utils/themes.js` and emits `src/utils/themes.css`:
  - `:root` block + `[data-theme="light"]` block from tokens (kebab-case mapping, e.g. `bgSecondary` → `--theme-background-secondary`).
  - `--glow-*` vars built from token primaries.
  - Leaflet dark-theme overrides using `var(--theme-*)`.
  - Header comment: `AUTO-GENERATED from src/utils/themes.js — do not edit by hand. Run: npm run generate:theme`.
- Add npm scripts: `"generate:theme": "node scripts/generate-theme-css.mjs"`, wired into `predev` and `prebuild` so it stays fresh.
- Commit the generated file; regenerate and diff against the current file to confirm the divergence (Phase 0–1 restores equivalence).

## Phase 2: Global CSS De-Hardcode

- `src/index.css`: replace hardcoded amber `hsla(45, 100%, 58%, …)` and `#FFB84D` with `var(--theme-primary)`/`var(--theme-*)`; body grid uses a generated accent-at-alpha var (add e.g. `--theme-primary-alpha` tokens or `color-mix()`).
- `src/utils/themes.css` Leaflet rules: use `var(--theme-*)` (generator handles it).
- Confirm `.glass`, `.glass-panel`, `.terminal`, select chevron, `grid-bg`, glows all resolve from vars.

## Phase 3: Component Sweep

- `TacticalPanelVariant2/4/5/6/7.jsx`: drop `amberColor` consts → `text-fui-accent` / `var(--theme-primary)`.
- `TacticalPanelVariant3.jsx`: `rgba(234,179,8,0.4)` shadow → `var(--glow)`/fui token.
- `LocationPanel.jsx`: `#eab308` → `themeColors` from `useTheme()` (or `var(--theme-primary)` in style props).
- `ProjectTreeViz.jsx`: `#eab308` border → theme token.
- `Matrix.jsx`: replace hardcoded "Yellow accent" copy with dynamic value from `getThemeColors()`.
- Grep audit: `grep -rn "hsl(\|hsla(\|#[0-9a-fA-F]\{3,8\}\|rgba(" src` should return **only** `themes.js` (and generated `themes.css` header exceptions).

## Phase 4: Verification & Docs

- `npm run generate:theme` → `git diff` should be no-op after Phase 1.
- `npm run lint` and `npm run build` pass.
- Manual: boot frontend, toggle dark/light (themes.css + Tailwind colors agree), spot-check Core.jsx SVG colors, map markers, glows, select dropdowns.
- Update `implementation_plan.md` Phase 0 to reference this centralization as the prerequisite re-theme mechanism.
