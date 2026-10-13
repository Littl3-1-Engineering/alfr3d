# Frontend `npm run lint` crashes on startup

## Status: 🟡 Crash fixed 2026-10-13 (`eslint.config.js` uses `reactHooks.configs.flat.recommended`; `UpdateBanner.jsx` unused catch bindings). `npm run lint` now exits 0 with 51 warnings. The React Compiler rules are downgraded to warnings and still need a refactor.

`cd services/service_frontend && npm run lint` dies loading `eslint.config.js`:

    TypeError: reactHooks.configs.flat/recommended is not iterable

So the frontend has not been linted since `eslint-plugin-react-hooks` moved its flat config.
`lint.sh` and the pre-commit hooks call this, and AGENTS.md lists it as a required step.

## Work items

- [ ] Check the installed `eslint-plugin-react-hooks` version against its docs: newer majors expose
      `reactHooks.configs.flat.recommended` (an object, not an array), older ones
      `configs['recommended-latest']`. Spread/use it the way that version expects.
- [ ] Run lint, fix or consciously disable what it newly reports (it has not run for a while).
- [ ] Check CI: it runs `npm ci` and tests but not lint; consider adding a lint step once it works.

## Resolution (2026-10-13)

- The crash: `eslint-plugin-react-hooks` 7 exposes `configs.flat.recommended` as a single config object;
  the old `...reactHooks.configs['flat/recommended']` spread no longer exists.
- Once lint ran again it reported 4 real `no-unused-vars` errors (fixed) and 43 errors from the React
  Compiler rules `recommended` now includes. Those are downgraded to `warn` in `eslint.config.js`
  because fixing them means rewriting effect logic in ~15 components that tests do not cover.

## Still open: the 51 warnings

| Rule | Count | Pattern |
|---|---|---|
| `react-hooks/set-state-in-effect` | 24 | setState called synchronously in an effect (Blueprint, CameraStream, ContainerHealth, ControlBlade, Core, DeviceRegistry, Domain, Profile, ...) |
| `react-hooks/exhaustive-deps` | 8 | missing effect dependencies |
| `react-hooks/refs` | 5 | ref read/written during render (AudioPlayer, AudioVisualizer, ThemeSync) |
| `react-hooks/immutability` | 5 | mutating values after render |
| `react-hooks/static-components` | 5 | components defined inside a component (`System.jsx`) |
| `react-hooks/purity` | 3 | impure calls (`Date.now()`) during render (AudioVisualizer, WeatherPanel) |
| `react-hooks/preserve-manual-memoization` | 1 | ControlBlade |

- [ ] Refactor component by component, checking each in the browser, then flip its rule back to `error`.
- [ ] Add `npm run lint` to the CI frontend job once the warning count is small.
